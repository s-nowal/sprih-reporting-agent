"""Research Agent — deep_agent for ESG web research.

Uses ``create_deep_agent`` which includes built-in middleware for:
- ``TodoListMiddleware``: ``write_todos`` tool so the agent can track its plan.
- ``FilesystemMiddleware``: file read/write tools (useful when saving research notes).
- ``SummarizationMiddleware``: automatic context-window management for long runs.
- ``AnthropicPromptCachingMiddleware``: prompt caching to reduce latency and cost.

When used as a subagent of the Reporting Agent via ``CompiledSubAgent``,
pass ``checkpointer=None`` — the parent agent manages state. The parent
also passes its own ``S3Backend`` (typically wrapped with a policy that
restricts writes to ``/research/``) via ``backend`` so that files written
by this agent are visible to the parent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from deepagents import create_deep_agent

from backend.ai.prompts.agents.research import RESEARCH_SYSTEM_PROMPT
from backend.ai.tools.cite_source import cite_source
from backend.ai.tools.web_fetch import web_fetch
from backend.ai.tools.web_search import web_search

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def build_research_graph(
    checkpointer: BaseCheckpointSaver | None = None,
    backend: Any | None = None,
):
    """Build and return the compiled research agent graph.

    Args:
        checkpointer: State checkpointer for interrupt/resume and thread
            persistence. Pass ``None`` when the graph is used as a subagent
            (the parent agent's checkpointer handles state).
        backend: Optional deepagents backend (or backend factory callable)
            for file operations. When ``None``, ``create_deep_agent``
            falls back to its default ``StateBackend`` (files in graph
            state). When the parent reporting agent invokes this graph as
            a subagent, it passes a shared ``S3Backend`` so the
            ``research/summary.md`` and ``research/citations/`` files
            land in the same workspace the parent reads from.

    Returns:
        A compiled deep agent ``StateGraph`` with built-in todo, filesystem,
        summarization, and prompt-caching middleware.
    """
    kwargs: dict[str, Any] = {
        "model": "anthropic:claude-sonnet-4-6",
        "tools": [web_search, web_fetch, cite_source],
        "system_prompt": RESEARCH_SYSTEM_PROMPT,
        "checkpointer": checkpointer,
        "name": "research-agent",
        "subagents": [],  # disable the auto-added general-purpose subagent
    }
    if backend is not None:
        kwargs["backend"] = backend
    return create_deep_agent(**kwargs)
