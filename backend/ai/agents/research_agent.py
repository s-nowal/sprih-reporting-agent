"""Research Agent — LangGraph ReAct agent for ESG web research.

Uses ``create_react_agent`` to build a simple think → tool → think loop.
The agent decides when to search, what to crawl, and when it has enough
information.  All per-request state lives in the checkpointer (keyed by
thread_id); the graph itself is stateless and created once at startup.
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import create_react_agent

from backend.ai.prompts.agents.research import RESEARCH_SYSTEM_PROMPT
from backend.ai.tools.web_crawl import web_crawl
from backend.ai.tools.web_search import web_search

_checkpointer = MemorySaver()


def build_research_graph():
    """Build and return the compiled research agent graph (singleton-safe)."""
    return create_react_agent(
        model="anthropic:claude-sonnet-4-20250514",
        tools=[web_search, web_crawl],
        prompt=RESEARCH_SYSTEM_PROMPT,
        checkpointer=_checkpointer,
        name="research-agent",
    )
