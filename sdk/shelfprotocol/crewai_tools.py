"""
Shelf Protocol as CrewAI tools.

    pip install "shelfprotocol[crewai]"

    from crewai import Agent
    from shelfprotocol.crewai_tools import get_tools

    buyer = Agent(
        role="Purchasing agent",
        goal="Buy what the user asked for, without spending past what the merchant allows",
        tools=get_tools(),
    )

The crew can find merchants and read catalogs, and shelf_can_buy gates the
actual spend against the merchant's own declared ceiling and verification state.

Point at a non-default registry (self-hosted, staging) with the SHELF_URL
environment variable, same as the plain SDK.
"""

from __future__ import annotations

from typing import List

from crewai.tools import BaseTool
from crewai.tools import tool as _crew_tool

from .agent_tools import DEFAULT_PREFIX, tool_specs


def get_tools(prefix: str = DEFAULT_PREFIX) -> List[BaseTool]:
    """Return the Shelf Protocol tools as CrewAI `BaseTool`s.

    Names are prefixed with "shelf_" by default so they don't collide with the
    generic `search`/`products` tools common in agent stacks; pass prefix="" if
    you'd rather have the bare names.
    """
    tools = []
    for spec in tool_specs(prefix):
        tool = _crew_tool(spec.name)(spec.func)
        # CrewAI derives the description from the function docstring. It's the
        # same text tool_specs already carries, but set it explicitly so the
        # LLM-visible description can't drift from the shared spec.
        tool.description = spec.description
        tools.append(tool)
    return tools


__all__ = ["get_tools"]
