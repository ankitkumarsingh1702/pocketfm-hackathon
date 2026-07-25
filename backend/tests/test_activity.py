"""Offline tests for the DB / Memory activity feed — no Neo4j, no LLM.

Covers the in-process ring buffer that records graph reads/writes: ordering,
the newest-N limit, and that recording tolerates the disabled flag.
"""

from __future__ import annotations

from app.db import activity
from app.db.activity import clear_activity, get_recent_activity, record_activity


def test_records_and_preserves_order_oldest_first():
    clear_activity()
    record_activity("read", "fetch_canon_subgraph", "Writers' Room", "read 5 nodes", {"nodes": 5})
    record_activity("write", "write_audience_verdict", "Audience", "wrote verdict", {"segments": 3})

    events = get_recent_activity(10)
    assert [e["op"] for e in events] == ["read", "write"]
    assert events[0]["source"] == "Writers' Room"
    assert events[-1]["fn"] == "write_audience_verdict"
    # Sequence numbers are monotonic and each event is timestamped.
    assert events[0]["seq"] < events[1]["seq"]
    assert all(isinstance(e["ts"], float) for e in events)


def test_limit_returns_newest_events():
    clear_activity()
    for i in range(5):
        record_activity("read", "fn", "src", f"e{i}")
    last_two = get_recent_activity(2)
    assert [e["detail"] for e in last_two] == ["e3", "e4"]
    assert get_recent_activity(0) == []


def test_recording_respects_disabled_flag(monkeypatch):
    clear_activity()
    monkeypatch.setattr(activity.settings, "use_activity_log", False)
    record_activity("read", "fn", "src", "should not be recorded")
    assert get_recent_activity(10) == []
