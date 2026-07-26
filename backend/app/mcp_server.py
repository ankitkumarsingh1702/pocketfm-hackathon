"""MCP server — every studio agent as a callable Model Context Protocol entity.

Exposes the persisted listener-agent population over MCP so any client (Claude
Desktop, Cursor, an agent framework, …) can search the roster, read an agent's
profile + memory, and *talk to* any one of the thousands of agents (it reacts in
character and remembers). Mounted at ``/mcp`` on the Simulated Studio service.

Stateless HTTP transport is used deliberately: Cloud Run may route each request
to a different instance, so there is no server-side session to keep sticky.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from app.lenses.audience_sim import react_one_agent
from app.schemas import Story

mcp = FastMCP(
    "PocketFM Simulated Studio",
    stateless_http=True,
    # Serve the streamable-HTTP endpoint at the sub-app root so mounting it at
    # "/mcp" yields exactly "/mcp" (not "/mcp/mcp").
    streamable_http_path="/",
    # This is a public, hosted MCP server behind Cloud Run's own domain, so the
    # SDK's default DNS-rebinding Host allow-list (localhost only) would 421 every
    # real request. Disable it; the endpoint is read-mostly and unauthenticated
    # by design for the demo.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@mcp.tool()
async def list_agents(
    query: str = "", segment: str = "", city: str = "", limit: int = 20
) -> list[dict]:
    """Search the listener-agent population.

    Returns compact agent cards (id, name, segment, city, age, genres, traits,
    memory_count). Filter by free-text `query`, `segment`, and/or `city`.
    """
    from app.graph.audience_store import load_audience_members_page

    return await load_audience_members_page(
        limit=max(1, min(int(limit), 50)),
        offset=0,
        q=query or None,
        segment=segment or None,
        city=city or None,
        source="MCP",
    )


@mcp.tool()
async def get_agent(agent_id: str) -> dict:
    """Get one agent's full profile + its remembered reactions (its history)."""
    from app.graph.audience_store import get_audience_member, recall_member_memory

    persona = await get_audience_member(agent_id)
    if persona is None:
        return {"error": "Agent not found", "agent_id": agent_id}
    memory = await recall_member_memory(agent_id, limit=25)
    return {"profile": persona.model_dump(), "memory": memory, "memory_count": len(memory)}


@mcp.tool()
async def ask_agent(agent_id: str, teaser: str, title: str = "Untitled post") -> dict:
    """Show a teaser/post to ONE agent; it reacts in character and remembers it.

    Returns the agent's reaction: hook_score (0-100), sentiment, engagement,
    emotion, a public comment in its own voice, and its private `reasoning`.
    """
    view = await react_one_agent(agent_id, Story(title=title, text=teaser), source="MCP")
    if view is None:
        return {"error": "Agent not found", "agent_id": agent_id}
    return view


@mcp.tool()
async def edit_agent(
    agent_id: str,
    name: str = "",
    city: str = "",
    segment: str = "",
    gender: str = "",
    age: int = 0,
    genres: list[str] | None = None,
    traits: list[str] | None = None,
    bio: str = "",
) -> dict:
    """Edit an existing agent's profile — only the fields you pass change.

    The agent keeps its id and its whole memory/history. Example: move an agent
    to a new city with edit_agent(agent_id, city="Delhi"). Get the agent_id from
    list_agents or get_agent. `bio` overwrites the persona/system prompt.
    """
    from app.graph.audience_store import recall_member_memory, update_audience_member

    persona = await update_audience_member(
        agent_id,
        name=name or None,
        city=city or None,
        segment=segment or None,
        gender=gender or None,
        age=age or None,
        genres=genres or None,
        traits=traits or None,
        system_prompt=bio or None,
        source="MCP",
    )
    if persona is None:
        return {"error": "Agent not found", "agent_id": agent_id}
    memory = await recall_member_memory(agent_id, limit=25)
    return {"updated": True, "profile": persona.model_dump(), "memory_count": len(memory)}


@mcp.tool()
async def create_agent(
    name: str,
    segment: str = "",
    city: str = "",
    gender: str = "",
    age: int = 0,
    genres: list[str] | None = None,
    traits: list[str] | None = None,
    bio: str = "",
) -> dict:
    """Create a brand-new listener agent and add it to the population.

    Returns the new agent's id + profile. If `bio` is omitted, a persona prompt
    is generated from the city/segment/genres/traits so the agent can react.
    """
    from app.graph.audience_store import create_audience_member

    persona = await create_audience_member(
        name=name,
        segment=segment or None,
        city=city or None,
        gender=gender or None,
        age=age or None,
        genres=genres or None,
        traits=traits or None,
        system_prompt=bio or None,
        source="MCP",
    )
    if persona is None:
        return {"error": "Could not create agent (graph unavailable)"}
    return {"created": True, "profile": persona.model_dump()}


@mcp.tool()
async def forget_agent(agent_id: str) -> dict:
    """Clear ONE agent's reaction history (memory) — handy to reset a demo.

    Removes only that agent's past reactions; the agent itself stays. Returns
    how many memories were cleared.
    """
    from app.graph.audience_store import get_audience_member, reset_member_memory

    persona = await get_audience_member(agent_id)
    if persona is None:
        return {"error": "Agent not found", "agent_id": agent_id}
    deleted = await reset_member_memory(agent_id, source="MCP")
    return {"agent_id": agent_id, "forgotten": deleted}


@mcp.tool()
async def audience_overview() -> dict:
    """Population overview: total agents + top segments, cities, genres, genders.

    Call this first to discover what values to search/filter by in list_agents.
    """
    from app.graph.audience_store import audience_facets

    return await audience_facets()


@mcp.resource("agent://{agent_id}")
async def agent_resource(agent_id: str) -> str:
    """Each agent as a first-class MCP resource: profile + memory as JSON."""
    from app.graph.audience_store import get_audience_member, recall_member_memory

    persona = await get_audience_member(agent_id)
    if persona is None:
        return json.dumps({"error": "Agent not found", "agent_id": agent_id})
    memory = await recall_member_memory(agent_id, limit=25)
    return json.dumps(
        {"profile": persona.model_dump(), "memory": memory}, ensure_ascii=False, indent=2
    )
