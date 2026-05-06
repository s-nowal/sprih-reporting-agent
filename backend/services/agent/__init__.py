"""Agent runtime sub-package — execution, threads, workspace.

Sub-modules:
- base, langgraph_service: AgentService interface and LangGraph implementation (THE SWAP POINT)
- thread: Agent Protocol thread CRUD (create, get, search, update, delete)
- workspace: temp workspace checkout/commit lifecycle for agent runs

Import the execution interface from here:

    from backend.services.agent import AgentService, get_agent_service, init_agent_service

Import sub-modules directly for thread/workspace operations:

    from backend.services.agent import thread as thread_service
    from backend.services.agent import workspace as workspace_service
"""

from backend.services.agent.base import AgentService
from backend.services.agent.langgraph_service import (
    get_agent_service,
    init_agent_service,
)

__all__ = ["AgentService", "get_agent_service", "init_agent_service"]
