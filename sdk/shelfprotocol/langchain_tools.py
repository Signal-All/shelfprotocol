"""
Shelf Protocol as LangChain tools.

    pip install "shelfprotocol[langchain]"

    from langchain.agents import create_agent
    from shelfprotocol.langchain_tools import get_tools

    agent = create_agent(model, tools=get_tools())

Now the agent can find merchants, read their catalogs, and — before it spends
anything — call shelf_can_buy to check the purchase against the limits the
merchant itself declared.

Point at a non-default registry (self-hosted, staging) with the SHELF_URL
environment variable, same as the plain SDK.
"""

from __future__ import annotations

from typing import List

from langchain_core.tools import BaseTool, StructuredTool

from .agent_tools import DEFAULT_PREFIX, tool_specs


def get_tools(prefix: str = DEFAULT_PREFIX) -> List[BaseTool]:
    """Return the Shelf Protocol tools as LangChain `StructuredTool`s.

    Names are prefixed with "shelf_" by default so they don't collide with the
    generic `search`/`products` tools common in agent stacks; pass prefix="" if
    you'd rather have the bare names.
    """
    return [
        StructuredTool.from_function(
            func=spec.func,
            name=spec.name,
            description=spec.description,
        )
        for spec in tool_specs(prefix)
    ]


__all__ = ["get_tools"]
