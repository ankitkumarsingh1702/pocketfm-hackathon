"""Offline coverage for the stateful Cliffhanger Planner swarm."""

from __future__ import annotations

from app.engine.cache import Cache
from app.engine.cliffhanger_swarm import (
    build_cliffhanger_prompt,
    ci95,
    mean_score,
    retry_delay_seconds,
    stratified_sample,
)
from app.engine.search import beam_search
from app.schemas import (
    CanonGraph,
    CanonNodeView,
    CliffhangerAgentVerdict,
    CliffhangerRating,
    Persona,
    Story,
)


def _persona(index: int, segment: str) -> Persona:
    return Persona(
        id=f"listener-{index}",
        name=f"Listener {index}",
        kind="audience",
        segment=segment,
        city="Mumbai",
        genres=["thriller"],
        system_prompt="You are a returning thriller listener.",
    )


def test_score_math_and_stratified_sample():
    ratings = [
        CliffhangerRating(
            candidate_id="root", hook_score=40, will_continue=False, reason="slow"
        ),
        CliffhangerRating(
            candidate_id="root", hook_score=60, will_continue=True, reason="okay"
        ),
        CliffhangerRating(
            candidate_id="root", hook_score=80, will_continue=True, reason="strong"
        ),
    ]
    assert mean_score(ratings) == 60.0
    assert ci95(ratings) > 0

    members = [
        _persona(0, "Metro"),
        _persona(1, "Metro"),
        _persona(2, "Town"),
        _persona(3, "Town"),
    ]
    sample = stratified_sample(members, 2)
    assert {member.segment for member in sample} == {"Metro", "Town"}


def test_retry_delay_uses_longer_quota_backoff(monkeypatch):
    monkeypatch.setattr(
        "app.engine.cliffhanger_swarm.random.random",
        lambda: 0.5,
    )

    assert retry_delay_seconds(Exception("429 RESOURCE_EXHAUSTED"), 0) == 7.5
    assert retry_delay_seconds(Exception("temporary 503"), 0) == 0.75
    assert retry_delay_seconds(Exception("429 RESOURCE_EXHAUSTED"), 8) == 45.0


def test_prompt_explains_paired_context_and_memory():
    system, prompt = build_cliffhanger_prompt(
        _persona(0, "Metro"),
        Story(title="Andhera", episode="4", text="Full episode. Weak close."),
        "Weak close.",
        [("root", "Weak close."), ("c1", "The lock turns.")],
        canon="Meera's sister died three years ago.",
        memory=[
            {
                "post": "Episode 3",
                "sentiment": "love",
                "engagement": "binge",
                "comment": "hooked",
            }
        ],
    )
    assert "Required ids: root, c1" in system
    assert "COMPLETE EPISODE CONTEXT" in prompt
    assert "YOUR HISTORY WITH THIS SHOW" in prompt
    assert "SHARED STORY CANON" in prompt


async def test_beam_search_uses_scout_then_full_matched_panel(monkeypatch, tmp_path):
    from app.engine import search

    members = [
        _persona(0, "Metro"),
        _persona(1, "Metro"),
        _persona(2, "Town"),
        _persona(3, "Town"),
    ]

    async def fake_resolve(_req):
        return members, "graph"

    async def fake_ready():
        return True

    async def fake_save(saved_members, **_kwargs):
        return len(saved_members)

    async def fake_fetch(*_args, **kwargs):
        assert kwargs["batch"] == "session-test"
        return CanonGraph(
            nodes=[
                CanonNodeView(
                    id="Character:meera",
                    label="Character",
                    name="Meera",
                )
            ]
        )

    async def fake_recall(ids, **_kwargs):
        return {
            member_id: ([{"post": "Ep 3"}] if member_id == "listener-0" else [])
            for member_id in ids
        }

    generated = 0

    async def fake_variants(_llm, _story, _ending, n):
        nonlocal generated
        out = []
        for _ in range(n):
            generated += 1
            out.append(f"Rewrite {generated}")
        return out

    async def fake_persist(*_args, **_kwargs):
        return True

    class FakeLLM:
        name = "fake"

        async def structured(self, system, prompt, schema, **_kwargs):
            assert schema is CliffhangerAgentVerdict
            ids = system.split("Required ids: ", 1)[1].rstrip(".").split(", ")
            return CliffhangerAgentVerdict(
                ratings=[
                    CliffhangerRating(
                        candidate_id=candidate_id,
                        hook_score=40
                        if prompt.split(f"[{candidate_id}]\n", 1)[1].startswith(
                            "Weak close."
                        )
                        else 80,
                        will_continue=not prompt.split(f"[{candidate_id}]\n", 1)[
                            1
                        ].startswith("Weak close."),
                        reason="matched listener judgment",
                    )
                    for candidate_id in ids
                ]
            )

    monkeypatch.setattr(search, "resolve_audience", fake_resolve)
    monkeypatch.setattr(search, "_stateful_graph_ready", fake_ready)
    monkeypatch.setattr(search, "save_audience_members", fake_save)
    monkeypatch.setattr(search, "fetch_canon_subgraph", fake_fetch)
    monkeypatch.setattr(search, "render_canon_memory", lambda _graph: "shared canon")
    monkeypatch.setattr(search, "recall_members_memories", fake_recall)
    monkeypatch.setattr(search, "_variants", fake_variants)
    monkeypatch.setattr(search, "persist_experiment_memory", fake_persist)

    events: list[dict] = []
    tree = await beam_search(
        Story(title="Andhera", episode="4", text="Full episode. Weak close."),
        "Weak close.",
        FakeLLM(),
        Cache(str(tmp_path)),
        beam_width=2,
        depth=2,
        panel_size=4,
        scout_size=2,
        finalist_count=1,
        canon_batch="session-test",
        on_event=events.append,
    )

    assert tree.panel_requested == 4
    assert tree.panel_actual == 4
    assert tree.panel_completed == 4
    assert tree.panel_dropped == 0
    assert tree.memory_hits == 1
    assert tree.audience_source == "graph"
    assert tree.best_id != "root"
    assert tree.baseline_score == 40.0
    assert tree.finalist_count == 1
    assert tree.planned_evaluations == 22  # 2 scouts × 7 arms + 4 agents × 2 arms
    assert tree.completed_evaluations == 22
    assert tree.experiment_archived is True
    assert tree.canon_scope == "session"
    assert tree.canon_nodes_loaded == 1
    assert tree.verification_cached_agents == 0
    assert any(event["type"] == "agent_scored" for event in events)
    assert any(
        event["type"] == "candidate_scored" and event["stage"] == "verified"
        for event in events
    )
