"""Research Agent — LangGraph ReAct agent for ESG web research.

Uses ``create_react_agent`` to build a simple think → tool → think loop.
The agent decides when to search, what to crawl, and when it has enough
information.  All per-request state lives in the checkpointer (keyed by
thread_id); the graph itself is stateless and created once at startup.

When used as a subagent of the Reporting Agent via ``CompiledSubAgent``,
pass ``checkpointer=None`` — the parent agent manages state.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain.agents import create_agent as create_react_agent

from backend.ai.prompts.agents.research import RESEARCH_SYSTEM_PROMPT
from backend.ai.tools.web_crawl import web_crawl
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
        A compiled LangGraph ``StateGraph`` with ``MessagesState``.
    """
    return create_react_agent(
        model="anthropic:claude-sonnet-4-20250514",
        tools=[web_search, web_crawl],
        system_prompt=RESEARCH_SYSTEM_PROMPT,
        checkpointer=checkpointer,
        name="research-agent",
    )
