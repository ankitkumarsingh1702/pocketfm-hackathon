"""A tiny async state-graph engine — the "agentic framework" primitive.

Nodes are async functions ``fn(state) -> state``; edges carry an optional
condition ``fn(state) -> bool``. ``run`` walks from the entry node, evaluating
outgoing edges in order to pick the next node, emitting an event per node and
transition. A ``max_steps`` cap and a per-node visit cap bound any loop, so the
showrunner's fix→re-simulate cycle can never run away.

This is deliberately ~90 lines and dependency-free: the workflow is one fixed
DAG with a single bounded loop, and the existing NDJSON streaming already gives
us the live-agent UI. A heavier framework (LangGraph) would add a large
dependency tree and fight the provider-agnostic ``LLMClient`` design for no gain.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

NodeFn = Callable[[dict], Awaitable[dict]]
CondFn = Callable[[dict], bool]


class StateGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, NodeFn | None] = {}
        self._edges: dict[str, list[tuple[CondFn | None, str]]] = {}
        self._entry: str | None = None

    def add_node(self, name: str, fn: NodeFn | None = None) -> None:
        self._nodes[name] = fn
        self._edges.setdefault(name, [])

    def add_edge(self, src: str, dst: str, cond: CondFn | None = None) -> None:
        self._edges.setdefault(src, []).append((cond, dst))

    def set_entry(self, name: str) -> None:
        self._entry = name

    async def run(
        self,
        state: dict,
        on_event: Callable[[dict], None] | None = None,
        max_steps: int = 16,
        max_visits: int = 4,
    ) -> dict:
        """Execute the graph from the entry node, returning the final state."""

        def emit(event: dict) -> None:
            if on_event:
                on_event(event)

        current = self._entry
        steps = 0
        visits: dict[str, int] = {}

        while current and steps < max_steps:
            steps += 1
            visits[current] = visits.get(current, 0) + 1
            if visits[current] > max_visits:
                emit({"type": "halted", "node": current, "reason": "visit cap"})
                break

            emit({"type": "node_started", "node": current, "step": steps})
            fn = self._nodes.get(current)
            if fn is not None:
                result = await fn(state)
                if result is not None:
                    state = result
            emit({"type": "node_done", "node": current, "step": steps})

            nxt: str | None = None
            for cond, dst in self._edges.get(current, []):
                if cond is None or cond(state):
                    nxt = dst
                    break
            if nxt:
                emit({"type": "transition", "from": current, "to": nxt})
            current = nxt

        return state
