"""Thread CRUD endpoints (Agent Protocol compatible)."""

from fastapi import APIRouter, Depends, Response

from backend.handlers import thread_handler
from backend.handlers.thread_handler import _ensure_thread
from backend.schemas.threads import (
    ThreadCreate,
    ThreadResponse,
    ThreadSearch,
    ThreadUpdate,
)
from backend.security.auth import EnterpriseContext, get_enterprise_context

router = APIRouter(tags=["threads"])


# --- Agent Protocol standard paths (used by deep-agent-ui / langgraph-sdk) ---


@router.post("/threads", response_model=ThreadResponse, status_code=201)
async def create_thread(
    data: ThreadCreate = ThreadCreate(),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await thread_handler.create_thread(data, enterprise)


router.add_api_route(  # alias: /threads/create
    "/threads/create", create_thread, methods=["POST"], include_in_schema=False
)


@router.post("/threads/search", response_model=list[ThreadResponse])
async def search_threads(
    data: ThreadSearch = ThreadSearch(),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await thread_handler.search_threads(data, enterprise)


router.add_api_route(  # alias: /threads/all
    "/threads/all", search_threads, methods=["GET"], include_in_schema=False
)


@router.get("/threads/{thread_id}/state")
async def get_thread_state(
    thread_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """Return current thread state. SDK calls this for state hydration.

    Auto-creates the thread if it doesn't exist so stale thread IDs from the
    frontend (e.g. after a server restart) don't produce unrecoverable 404s.
    """
    t = await _ensure_thread(thread_id, enterprise)
    return {"values": t.get("values", {}), "next": [], "checkpoint": None}


@router.post("/threads/{thread_id}/history")
async def get_thread_history(
    thread_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """Return checkpoint history. Auto-creates thread if missing; returns empty list."""
    await _ensure_thread(thread_id, enterprise)
    return []


@router.get("/threads/{thread_id}", response_model=ThreadResponse)
async def get_thread(
    thread_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await thread_handler.get_thread(thread_id, enterprise)


@router.patch("/threads/{thread_id}", response_model=ThreadResponse)
async def update_thread(
    thread_id: str,
    data: ThreadUpdate,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await thread_handler.update_thread(thread_id, data, enterprise)


router.add_api_route(  # alias: /threads/{thread_id}/update
    "/threads/{thread_id}/update", update_thread, methods=["PATCH"],
    include_in_schema=False,
)


@router.delete("/threads/{thread_id}", status_code=204)
async def delete_thread(
    thread_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    await thread_handler.delete_thread(thread_id, enterprise)
    return Response(status_code=204)


router.add_api_route(  # alias: /threads/{thread_id}/delete
    "/threads/{thread_id}/delete", delete_thread, methods=["DELETE"],
    include_in_schema=False,
)
