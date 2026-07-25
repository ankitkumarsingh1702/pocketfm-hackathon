"""Knowledge-graph package — Neo4j-backed story canon (shared agent memory).

Every accessor here is best-effort: when Neo4j is disabled or unreachable the
engine falls back to an empty canon and behaves exactly as it did before the
knowledge graph existed. See :mod:`app.graph.driver`.
"""
