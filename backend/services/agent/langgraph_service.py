"""Concrete AgentService backed by LangGraph.

Wraps LangGraph graph execution and provides the async generator that
the run handler consumes for SSE streaming.  New agent graphs are
registered in ``_build_graphs()``.

Module-level ``init_agent_service`` / ``get_agent_service`` follow the
same singleton pattern as the infra registry.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

from langgraph.types import Command

from backend.ai.agents.reporting_agent import build_reporting_graph
from backend.ai.agents.research_agent import build_research_graph
from backend.services.agent.base import AgentService

# Graphs that need a per-run workspace (built fresh each run)
_WORKSPACE_GRAPHS = {"reporting-agent"}


class LangGraphAgentService(AgentService):
    """Concrete agent service that delegates to LangGraph compiled graphs.

    Stateless graphs (research-agent) are built once at startup and cached.
    Workspace-dependent graphs (reporting-agent) are built per-run because
    the ``FilesystemBackend`` root differs for each thread's temp workspace.

    A single ``checkpointer`` is shared across all graphs so every thread
    accumulates a full conversation history that persists across server restarts.

    Args:
        checkpointer: LangGraph checkpointer for persistent thread state.
            Must support async operations (e.g. ``AsyncSqliteSaver``).
    """

    def __init__(self, checkpointer: Any) -> None:
        self._checkpointer = checkpointer
        self._cached_graphs: dict[str, Any] = {}
        self._build_cached_graphs()

    def _build_cached_graphs(self) -> None:
        """Build and cache graphs that don't depend on per-run state.

        The standalone research agent uses the shared checkpointer for thread
        state.  When used as a subagent of the reporting agent, the research
        graph is built without a checkpointer (the parent manages state).
        """
        self._cached_graphs["research-agent"] = build_research_graph(
            checkpointer=self._checkpointer
        )

    def _get_graph(
        self, graph_name: str, *, workspace_root: Path | None = None
    ) -> Any:
        """Return the compiled graph for ``graph_name``.

        For workspace-dependent graphs, a fresh graph is built using the
        provided ``workspace_root``.  For cached graphs, the pre-built
        instance is returned.

        Args:
            graph_name: Registered name (e.g. ``"research-agent"``).
            workspace_root: Required for workspace-dependent graphs
                (e.g. ``"reporting-agent"``).

        Returns:
            The compiled LangGraph ``StateGraph``.

        Raises:
            ValueError: If ``graph_name`` is unknown or workspace_root is
                missing for a workspace-dependent graph.
        """
        # --- Workspace-dependent graphs: built fresh per-run -----------------
        if graph_name in _WORKSPACE_GRAPHS:
            if workspace_root is None:
                raise ValueError(
                    f"Graph {graph_name!r} requires a workspace_root. "
                    f"Pass it via the workspace_root parameter."
                )
            if graph_name == "reporting-agent":
                return build_reporting_graph(workspace_root, self._checkpointer)
            raise ValueError(f"No builder for workspace graph {graph_name!r}")

        # --- Cached graphs: built once at startup ----------------------------
        graph = self._cached_graphs.get(graph_name)
        if graph is None:
            available = list(self._cached_graphs.keys()) + list(_WORKSPACE_GRAPHS)
            raise ValueError(
                f"Unknown graph {graph_name!r}. Available: {available}"
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
        job_id: str | None = None,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        """Invoke the graph and return the final state (non-streaming).

        Args:
            graph_name: Registered agent name (e.g. ``"research-agent"``).
            thread_id: Conversation thread for checkpointer state.
            input_data: Message dict passed to the graph (``{"messages": [...]}``)
            enterprise_id: Tenant id injected into tool config.
            job_id: Job id injected into tool config for provenance.
            workspace_root: Temp workspace path. Required for workspace-dependent
                graphs (e.g. ``"reporting-agent"``).

        Returns:
            The final state dict from the graph (``{"messages": [...]}``)

        Raises:
            ValueError: If ``graph_name`` is not registered.
        """
        graph = self._get_graph(graph_name, workspace_root=workspace_root)
        config = self._make_config(thread_id, enterprise_id, job_id)
        return await graph.ainvoke(input_data, config)

    async def stream(
        self,
        graph_name: str,
        thread_id: str,
        input_data: dict[str, Any] | None = None,
        *,
        enterprise_id: str = "dev-enterprise",
        job_id: str | None = None,
        command: dict[str, Any] | None = None,
        workspace_root: Path | None = None,
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
            job_id: Job id injected into tool config for provenance.
            command: Resume payload (``{"resume": <value>}``). When set,
                ``input_data`` is ignored and a ``Command`` is sent instead.
            workspace_root: Temp workspace path. Required for workspace-dependent
                graphs (e.g. ``"reporting-agent"``).

        Yields:
            State dicts (``{"messages": [...]}``) — one per graph step.

        Raises:
            ValueError: If ``graph_name`` is not registered.
        """
        graph = self._get_graph(graph_name, workspace_root=workspace_root)
        config = self._make_config(thread_id, enterprise_id, job_id)

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
        job_id: str | None = None,
        workspace_root: Path | None = None,
    ) -> dict[str, Any]:
        """Resume a graph from an interrupt with the given value.

        Args:
            graph_name: Registered agent name.
            thread_id: Conversation thread to resume.
            value: The user's response to the interrupt prompt.
            enterprise_id: Tenant id injected into tool config.
            job_id: Job id injected into tool config.
            workspace_root: Temp workspace path for workspace-dependent graphs.

        Returns:
            The final state dict from the resumed graph.
        """
        graph = self._get_graph(graph_name, workspace_root=workspace_root)
        config = self._make_config(thread_id, enterprise_id, job_id)
        return await graph.ainvoke(Command(resume=value), config)

    # -- Helpers ---------------------------------------------------------------

    @staticmethod
    def _make_config(
        thread_id: str,
        enterprise_id: str,
        job_id: str | None,
    ) -> dict:
        """Build the LangGraph ``RunnableConfig`` with per-request values.

        These values are available inside tools via
        ``config.get("configurable", {}).get("enterprise_id")``.

        Args:
            thread_id: Used by the checkpointer to scope conversation state.
            enterprise_id: Tenant id — scopes storage paths and DB rows.
            job_id: Links tool outputs to a parent job for provenance.

        Returns:
            A dict suitable for passing as the ``config`` arg to ``graph.ainvoke``
            or ``graph.astream``.
        """
        return {
            "configurable": {
                "thread_id": thread_id,
                "enterprise_id": enterprise_id,
                "job_id": job_id,
            },
            # LangSmith groups all runs with the same metadata.thread_id under
            # one conversation thread in the UI.
            "metadata": {"thread_id": thread_id},
        }


# -- Module-level singleton ---------------------------------------------------

_service: LangGraphAgentService | None = None


def init_agent_service(checkpointer: Any) -> None:
    """Create the singleton LangGraphAgentService. Called once at app startup.

    Args:
        checkpointer: Shared LangGraph checkpointer (e.g. ``AsyncSqliteSaver``)
            that persists thread state across server restarts and between runs.
    """
    global _service
    _service = LangGraphAgentService(checkpointer)


def get_agent_service() -> LangGraphAgentService:
    """Return the agent service. Raises if ``init_agent_service`` has not been called."""
    if _service is None:
        raise RuntimeError(
            "Agent service not initialised — call init_agent_service() at startup"
        )
    return _service
