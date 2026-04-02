"""Agent execution service — wraps langgraph (THE SWAP POINT).

When replacing langgraph with another framework, only this file changes.
"""

from collections.abc import AsyncGenerator
from typing import Any


class AgentService:
    async def run(
        self, graph_name: str, thread_id: str, input: dict[str, Any]
    ) -> dict[str, Any]:
        raise NotImplementedError

    async def stream(
        self, graph_name: str, thread_id: str, input: dict[str, Any]
    ) -> AsyncGenerator[dict, None]:
        raise NotImplementedError
        yield  # noqa: unreachable — makes this a generator

    async def resume(
        self, graph_name: str, thread_id: str, value: Any
    ) -> dict[str, Any]:
        raise NotImplementedError
