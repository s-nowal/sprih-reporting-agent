"""Research Agent — deep_agent for ESG web research.

Uses ``create_deep_agent`` which includes built-in middleware for:
- ``TodoListMiddleware``: ``write_todos`` tool so the agent can track its plan.
- ``FilesystemMiddleware``: file read/write tools (useful when saving research notes).
- ``SummarizationMiddleware``: automatic context-window management for long runs.
- ``AnthropicPromptCachingMiddleware``: prompt caching to reduce latency and cost.

When used as a subagent of the Reporting Agent via ``CompiledSubAgent``,
pass ``checkpointer=None`` — the parent agent manages state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from deepagents import create_deep_agent

from backend.ai.prompts.agents.research import RESEARCH_SYSTEM_PROMPT
from backend.ai.tools.web_fetch import web_fetch
from backend.ai.tools.web_search import web_search

if TYPE_CHECKING:
    from langgraph.checkpoint.base import BaseCheckpointSaver


def build_research_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Build and return the compiled research agent graph.

    Args:
        checkpointer: State checkpointer for interrupt/resume and thread
            persistence. Pass ``None`` when the graph is used as a subagent
            (the parent agent's checkpointer handles state).

    Returns:
        A compiled deep agent ``StateGraph`` with built-in todo, filesystem,
        summarization, and prompt-caching middleware.
    """
    return create_deep_agent(
        model="anthropic:claude-sonnet-4-6",
        tools=[web_search, web_fetch],
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        checkpointer=checkpointer,
        name="research-agent",
        subagents=[],  # disable the auto-added general-purpose subagent
    )
