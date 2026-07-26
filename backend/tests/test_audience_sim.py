"""Offline tests for the Audience Simulator ("Living Audience").

Pure-function coverage — no network, no LLM, no graph. Verifies the simulator
aggregation math, the multimodal/memory prompt assembly, the reaction view
mapping, virality ordering, post keying, and the generator's offline fallback.
"""

from __future__ import annotations

from app.engine.aggregate import aggregate_sim, reaction_view
from app.engine.audience_agent import build_social_prompt
from app.graph.audience_store import post_key
from app.lenses.audience_sim import resolve_canon
from app.schemas import Persona, SocialReaction, Story


def _persona(i: int, segment: str = "Metro Binge-Watcher") -> Persona:
    return Persona(
        id=f"a{i}",
        name=f"Listener {i}",
        kind="audience",
        segment=segment,
        age=25,
        city="Mumbai",
        genres=["thriller"],
        system_prompt="You are a PocketFM listener.",
    )


def _reaction(
    sentiment: str = "like",
    engagement: str = "like",
    hook: int = 70,
    listen: bool = True,
    comment: str = "nice",
    emotion: str = "curious",
    reasoning: str = "because",
    memory: str = "",
) -> SocialReaction:
    return SocialReaction(
        will_listen=listen,
        hook_score=hook,
        sentiment=sentiment,
        engagement=engagement,
        emotion=emotion,
        comment=comment,
        reasoning=reasoning,
        memory_note=memory,
    )


def test_aggregate_sim_basic():
    pairs = [
        (_persona(0, "Metro"), _reaction("love", "share", 95, True, "loved it")),
        (_persona(1, "Metro"), _reaction("like", "like", 70, True, "good")),
        (_persona(2, "Town"), _reaction("neutral", "scroll_past", 30, False, "")),
        (_persona(3, "Town"), _reaction("dislike", "scroll_past", 10, False, "meh")),
    ]
    res = aggregate_sim(pairs, dropped=2)

    assert res.total == 4
    assert res.dropped == 2
    assert res.listen_pct == 50.0                 # 2 of 4 would hit play
    assert abs(res.avg_hook_score - 51.25) < 0.1  # mean(95,70,30,10)
    # virality = mean(share=80, like=25, scroll_past=0, scroll_past=0) = 26.25
    assert abs(res.virality - 26.25) < 0.1

    # Distributions cover every reaction exactly once.
    assert sum(s.count for s in res.sentiment_breakdown) == 4
    assert sum(e.count for e in res.engagement_funnel) == 4

    assert {s.segment for s in res.segments} == {"Metro", "Town"}
    # Only non-empty comments become top comments.
    assert res.top_comments and all(v.comment for v in res.top_comments)
    assert len(res.reactions) == 4


def test_aggregate_sim_empty_is_safe():
    res = aggregate_sim([], dropped=0)
    assert res.total == 0
    assert res.listen_pct == 0.0
    assert res.avg_hook_score == 0.0
    assert res.virality == 0.0
    assert res.reactions == []
    assert res.segments == []


def test_aggregate_sim_reactions_capped():
    pairs = [(_persona(i), _reaction()) for i in range(120)]
    res = aggregate_sim(pairs, sample_size=80)
    assert res.total == 120
    assert len(res.reactions) == 80  # feed is capped; totals still reflect all 120


def test_build_social_prompt_multimodal_and_memory():
    persona = _persona(0)
    story = Story(
        title="Andhera Ep 5",
        text="A chilling teaser...",
        image_base64="Zm9v",
        image_mime="image/png",
    )
    memory = [
        {"post": "Andhera Ep 4", "sentiment": "love", "engagement": "share", "comment": "gripping!"}
    ]
    system, user = build_social_prompt(persona, story, canon="Naina is a detective.", memory=memory)

    assert system.startswith("You are Listener 0")
    assert "POST TITLE: Andhera Ep 5" in user
    assert "LOOK at it" in user                       # image note present
    assert "YOUR HISTORY WITH THIS CREATOR" in user   # memory recall present
    assert "WHAT YOU REMEMBER OF THE STORY SO FAR" in user  # canon present
    assert user.strip().endswith("React now.")


def test_build_social_prompt_text_only():
    system, user = build_social_prompt(_persona(1), Story(title="T", text="body"))
    assert "LOOK at it" not in user
    assert "YOUR HISTORY WITH THIS CREATOR" not in user
    assert user.strip().endswith("React now.")


def test_resolve_canon_prefers_client_recap_then_graph_then_empty():
    # The client's episode-scoped recap wins over the whole-show graph canon.
    assert resolve_canon("Ep1-5 recap", "whole-show bible", 2000) == "Ep1-5 recap"
    # Standalone post (no recap): fall back to graph canon.
    assert resolve_canon(None, "whole-show bible", 2000) == "whole-show bible"
    assert resolve_canon("", "whole-show bible", 2000) == "whole-show bible"
    # Neither available: empty (build_social_prompt then skips the canon slot).
    assert resolve_canon(None, None, 2000) == ""
    assert resolve_canon("", "", 2000) == ""


def test_resolve_canon_hard_caps_long_recap():
    # A long season's recap is bounded as defense-in-depth against token blowup.
    assert resolve_canon("x" * 5000, None, 2000) == "x" * 2000


def test_story_so_far_threads_into_prompt_via_canon_slot():
    # A posted episode carries story_so_far; it surfaces in the agent prompt so a
    # listener reacting to episode N is grounded in episodes 1..N-1.
    story = Story(
        title="The Ninth Ring",
        episode="Episode 6",
        text="Episode 6 teaser...",
        story_so_far="Episode 1: The Ledger Gap Opens\nEpisode 2: Line 9 Rings",
    )
    assert story.story_so_far  # field accepted by the schema
    canon = resolve_canon(story.story_so_far, None, 2000)
    _, user = build_social_prompt(_persona(0), story, canon=canon)
    assert "EPISODE: Episode 6" in user
    assert "WHAT YOU REMEMBER OF THE STORY SO FAR" in user
    assert "The Ledger Gap Opens" in user


def test_reaction_view_maps_fields():
    persona = _persona(7, "Gen-Z")
    r = _reaction("love", "subscribe", 88, True, "omg", "hooked", "the twist", "remembered ep4")
    view = reaction_view(persona, r)
    assert view.persona_id == "a7"
    assert view.name == "Listener 7"
    assert view.segment == "Gen-Z"
    assert view.hook_score == 88
    assert view.sentiment == "love"
    assert view.engagement == "subscribe"
    assert view.comment == "omg"
    assert view.reasoning == "the twist"
    assert view.memory_note == "remembered ep4"


def test_virality_orders_engagements():
    def vir(action: str) -> float:
        return aggregate_sim([(_persona(0), _reaction(engagement=action))]).virality

    assert (
        vir("scroll_past")
        < vir("like")
        < vir("share")
        < vir("subscribe")
        < vir("binge")
    )


def test_post_key_stable_and_content_sensitive():
    s1 = Story(title="Andhera", text="body one")
    s2 = Story(title="Andhera", text="body two")
    assert post_key(s1) == post_key(s1)              # deterministic
    assert post_key(s1).startswith("Post:andhera-")
    assert post_key(s1) != post_key(s2)              # content-sensitive


async def test_generate_personas_fallback_offline(monkeypatch):
    """With the LLM unavailable, generation falls back to archetype fan-out."""
    from app.personas import generator

    class _BoomLLM:
        name = "boom"

        async def structured(self, *args, **kwargs):
            raise RuntimeError("no network in tests")

    monkeypatch.setattr(generator, "get_llm", lambda: _BoomLLM())
    people = await generator.generate_personas(5)

    assert len(people) == 5
    assert all(p.kind == "audience" for p in people)
    assert len({p.id for p in people}) == 5  # unique ids even in fallback
