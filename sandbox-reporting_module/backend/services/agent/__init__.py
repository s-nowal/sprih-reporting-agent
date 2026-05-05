"""Agent execution service — the framework swap boundary.

Import from here rather than reaching into submodules directly:

    from backend.services.agent import AgentService, get_agent_service, init_agent_service
"""

from backend.services.agent.base import AgentService
from backend.services.agent.langgraph_service import (
    get_agent_service,
    init_agent_service,
)

__all__ = ["AgentService", "get_agent_service", "init_agent_service"]
