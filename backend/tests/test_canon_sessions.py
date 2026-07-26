"""Regression guards for safe, session-scoped Story Canon ownership."""

from __future__ import annotations

from dataclasses import dataclass

from app.graph import store
from app.schemas import (
    CanonExtraction,
    ExtractedEntity,
    ExtractedFact,
    ExtractedRelation,
    PlanRequest,
    Story,
)


@dataclass
class _Counters:
    nodes_created: int = 0
    relationships_created: int = 0
    nodes_deleted: int = 0
    relationships_deleted: int = 0


class _Summary:
    counters = _Counters()


class _Result:
    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration

    async def consume(self):
        return _Summary()

    async def single(self):
        return {"c": 0}


class _Session:
    def __init__(self, calls):
        self.calls = calls

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def run(self, query, **params):
        self.calls.append((query, params))
        return _Result()


class _Driver:
    def __init__(self):
        self.calls = []

    def session(self, **_kwargs):
        return _Session(self.calls)


def _extraction() -> CanonExtraction:
    return CanonExtraction(
        entities=[
            ExtractedEntity(
                key="meera",
                type="Character",
                name="Meera",
                description="A woman receiving an impossible call.",
            ),
            ExtractedEntity(
                key="anya",
                type="Character",
                name="Anya",
                description="Meera's late sister.",
            ),
        ],
        relations=[
            ExtractedRelation(
                source_key="anya",
                target_key="meera",
                type="WARNS",
                detail="Anya warns Meera.",
            )
        ],
        facts=[
            ExtractedFact(
                subject_key="anya",
                predicate="status",
                object="died three years ago",
            )
        ],
    )


async def test_two_sessions_use_memberships_not_mutable_node_ownership(monkeypatch):
    driver = _Driver()
    monkeypatch.setattr(store, "get_driver", lambda: driver)
    story = Story(title="Meera", episode="4", text="The dead sister calls.")

    await store.ingest_extraction(story, _extraction(), batch="session-a")
    await store.ingest_extraction(story, _extraction(), batch="session-b")

    queries = "\n".join(query for query, _ in driver.calls)
    membership_params = [
        params["batch"]
        for query, params in driver.calls
        if "MERGE (cb:CanonBatch" in query and "INCLUDES" in query
    ]
    assert membership_params == ["session-a", "session-b"]
    assert ".batch=" not in queries
    assert ".batch =" not in queries
    assert "r.batches" in queries


async def test_session_reads_never_fall_back_to_full_canon(monkeypatch):
    driver = _Driver()
    monkeypatch.setattr(store, "get_driver", lambda: driver)
    story = Story(title="Meera", episode="4", text="The dead sister calls.")

    await store.fetch_full_graph(batch="session-a")
    await store.fetch_canon_subgraph(story, source="test", batch="session-a")

    scoped_queries = [query for query, params in driver.calls if params.get("batch") == "session-a"]
    assert scoped_queries
    assert all("CanonBatch" in query for query in scoped_queries)
    assert any("$batch IN coalesce(r.batches, [])" in query for query in scoped_queries)


async def test_reset_is_membership_scoped_and_never_detach_deletes(monkeypatch):
    driver = _Driver()
    monkeypatch.setattr(store, "get_driver", lambda: driver)

    result = await store.reset_canon_batch("session-a")

    queries = "\n".join(query for query, _ in driver.calls)
    assert result.batch == "session-a"
    assert "DETACH DELETE" not in queries
    assert "CanonBatch {id:$batch}" in queries
    assert "n.seed_batch IS NULL" in queries
    assert "NOT EXISTS { MATCH (:CanonBatch)-[:INCLUDES]->(n) }" in queries
    assert all(
        params.get("batch") in {None, "session-a"}
        for _, params in driver.calls
    )


def test_planner_requires_a_valid_session_batch():
    request = PlanRequest(
        story=Story(title="Meera", episode="4", text="The dead sister calls."),
        weak_excerpt="The voice is her sister's.",
        batch="session-a",
    )
    assert request.batch == "session-a"
