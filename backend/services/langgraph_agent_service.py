"""Concrete AgentService backed by LangGraph.

Wraps LangGraph graph execution and provides the async generator that
the run handler consumes for SSE streaming.  New agent graphs are
registered in ``_build_graphs()``.

Module-level ``init_agent_service`` / ``get_agent_service`` follow the
same singleton pattern as the infra registry.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from langgraph.types import Command

from backend.ai.agents.research_agent import build_research_graph
from backend.services.agent_service import AgentService


class LangGraphAgentService(AgentService):
    """Concrete agent service that delegates to LangGraph compiled graphs."""

    def __init__(self) -> None:
        self._graphs: dict[str, Any] = {}
        self._build_graphs()

    def _build_graphs(self) -> None:
        """Register all available agent graphs."""
        self._graphs["research-agent"] = build_research_graph()

    def _get_graph(self, graph_name: str) -> Any:
        """Look up a compiled graph by name.

        Args:
            graph_name: Registered name (e.g. ``"research-agent"``).

        Returns:
            The compiled LangGraph ``StateGraph``.

        Raises:
            ValueError: If ``graph_name`` is not registered.
        """
        graph = self._graphs.get(graph_name)
        if graph is None:
            raise ValueError(
                f"Unknown graph {graph_name!r}. "
                f"Available: {list(self._graphs.keys())}"
            )
        return graph

    # -- Public API (implements AgentService) ----------------------------------

    async def run(
        self,
        graph_name: str,
        thread_id: str,
        input_data: dict[str, Any],
        *,
        enterprise_id: str = "dev-enterprise",
        research_job_id: str | None = None,
    ) -> dict[str, Any]:
        """Invoke the graph and return the final state (non-streaming).

        Args:
            graph_name: Registered agent name (e.g. ``"research-agent"``).
            thread_id: Conversation thread for checkpointer state.
            input_data: Message dict passed to the graph (``{"messages": [...]}``)
            enterprise_id: Tenant id injected into tool config.
            research_job_id: Job id injected into tool config for provenance.

        Returns:
            The final state dict from the graph (``{"messages": [...]}``)

        Raises:
            ValueError: If ``graph_name`` is not registered.
        """
        graph = self._get_graph(graph_name)
        config = self._make_config(thread_id, enterprise_id, research_job_id)
        return await graph.ainvoke(input_data, config)

    async def stream(
        self,
        graph_name: str,
        thread_id: str,
        input_data: dict[str, Any] | None = None,
        *,
        enterprise_id: str = "dev-enterprise",
        research_job_id: str | None = None,
        command: dict[str, Any] | None = None,
    ) -> AsyncGenerator[dict, None]:
        """Stream agent execution, yielding full state after each graph step.

        Uses ``graph.astream(stream_mode="values")`` which yields the complete
        state dict after every node execution. The handler converts each yield
        into an SSE ``values`` event for the frontend.

        If ``command`` is provided (resume from interrupt), a ``Command(resume=...)``
        is passed instead of ``input_data``.

        Args:
            graph_name: Registered agent name.
            thread_id: Conversation thread for checkpointer state.
            input_data: Message dict (ignored when ``command`` is set).
            enterprise_id: Tenant id injected into tool config.
            research_job_id: Job id injected into tool config for provenance.
            command: Resume payload (``{"resume": <value>}``). When set,
                ``input_data`` is ignored and a ``Command`` is sent instead.

        Yields:
            State dicts (``{"messages": [...]}``) — one per graph step.

        Raises:
            ValueError: If ``graph_name`` is not registered.
        """
        graph = self._get_graph(graph_name)
        config = self._make_config(thread_id, enterprise_id, research_job_id)

        agent_input: Any
        if command and command.get("resume") is not None:
            agent_input = Command(resume=command["resume"])
        else:
            agent_input = input_data or {}

        async for state in graph.astream(agent_input, config, stream_mode="values"):
            yield state

    async def resume(
        self,
        graph_name: str,
        thread_id: str,
        value: Any,
        *,
        enterprise_id: str = "dev-enterprise",
        research_job_id: str | None = None,
    ) -> dict[str, Any]:
        """Resume a graph from an interrupt with the given value.

        Args:
            graph_name: Registered agent name.
            thread_id: Conversation thread to resume.
            value: The user's response to the interrupt prompt.
            enterprise_id: Tenant id injected into tool config.
            research_job_id: Job id injected into tool config.

        Returns:
            The final state dict from the resumed graph.
        """
        graph = self._get_graph(graph_name)
        config = self._make_config(thread_id, enterprise_id, research_job_id)
        return await graph.ainvoke(Command(resume=value), config)

    # -- Helpers ---------------------------------------------------------------

    @staticmethod
    def _make_config(
        thread_id: str,
        enterprise_id: str,
        research_job_id: str | None,
    ) -> dict:
        """Build the LangGraph ``RunnableConfig`` with per-request values.

        These values are available inside tools via
        ``config.get("configurable", {}).get("enterprise_id")``.

        Args:
            thread_id: Used by the checkpointer to scope conversation state.
            enterprise_id: Tenant id — scopes storage paths and DB rows.
            research_job_id: Links tool outputs to a parent job for provenance.

        Returns:
            A dict suitable for passing as the ``config`` arg to ``graph.ainvoke``
            or ``graph.astream``.
        """
        return {
            "configurable": {
                "thread_id": thread_id,
                "enterprise_id": enterprise_id,
                "research_job_id": research_job_id,
            }
        }


# -- Module-level singleton ---------------------------------------------------

_service: LangGraphAgentService | None = None


def init_agent_service() -> None:
    """Create the singleton LangGraphAgentService. Called once at app startup."""
    global _service
    _service = LangGraphAgentService()


def get_agent_service() -> LangGraphAgentService:
    """Return the agent service. Raises if ``init_agent_service`` has not been called."""
    if _service is None:
        raise RuntimeError(
            "Agent service not initialised — call init_agent_service() at startup"
        )
    return _service
