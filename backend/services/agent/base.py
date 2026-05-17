"""Abstract agent service — the swap point for replacing LangGraph.

When replacing LangGraph with another framework, create a new module in this
package that implements ``AgentService`` and wire it into ``__init__.py``.
"""

from collections.abc import AsyncGenerator
from typing import Any


class AgentService:
    """Abstract interface for agent execution.

    All methods raise ``NotImplementedError`` — subclasses must override.
    """

    async def run(
        self,
        graph_name: str,
        thread_id: str,
        input_data: dict[str, Any],
        *,
        client_type: str = "browser",
    ) -> dict[str, Any]:
        """Invoke an agent graph and return the final state.

        Args:
            graph_name: Registered agent name (e.g. ``"research-agent"``).
            thread_id: Conversation thread for checkpointer state.
            input_data: Message dict (``{"messages": [...]}``)
            client_type: ``"word"`` or ``"browser"`` — selects the system prompt.

        Returns:
            Final state dict from the graph.

        Raises:
            NotImplementedError: Always — must be overridden.
        """
        raise NotImplementedError

    async def stream(
        self,
        graph_name: str,
        thread_id: str,
        input_data: dict[str, Any],
        *,
        client_type: str = "browser",
    ) -> AsyncGenerator[dict, None]:
        """Stream agent execution, yielding state after each step.

        Args:
            graph_name: Registered agent name.
            thread_id: Conversation thread for checkpointer state.
            input_data: Message dict (``{"messages": [...]}``)
            client_type: ``"word"`` or ``"browser"`` — selects the system prompt.

        Yields:
            State dicts — one per graph step.

        Raises:
            NotImplementedError: Always — must be overridden.
        """
        raise NotImplementedError
        yield  # noqa: unreachable — makes this a generator

    async def resume(
        self,
        graph_name: str,
        thread_id: str,
        value: Any,
        *,
        client_type: str = "browser",
    ) -> dict[str, Any]:
        """Resume a graph from an interrupt with the given value.

        Args:
            graph_name: Registered agent name.
            thread_id: Conversation thread to resume.
            value: The user's response to the interrupt prompt.
            client_type: ``"word"`` or ``"browser"`` — selects the system prompt.

        Returns:
            Final state dict from the resumed graph.

        Raises:
            NotImplementedError: Always — must be overridden.
        """
        raise NotImplementedError
