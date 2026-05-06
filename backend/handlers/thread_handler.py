"""Thread CRUD handler — delegates persistence to thread_service (MariaDB)."""

from uuid import uuid4

from fastapi import HTTPException

from backend.schemas.threads import (
    ThreadCreate,
    ThreadResponse,
    ThreadSearch,
    ThreadUpdate,
)
from backend.security.auth import EnterpriseContext
from backend.services.agent import thread as thread_service


def _to_response(t: dict) -> ThreadResponse:
    return ThreadResponse(**t)


async def _ensure_thread(thread_id: str, enterprise: EnterpriseContext) -> dict:
    """Return the thread if it exists and is owned by this enterprise; create it if not.

    Used by history/state/stream endpoints so a stale thread ID (e.g. from the
    frontend's URL after a server restart) is silently recreated rather than
    returning a 404 that the UI can't recover from on its own.

    Args:
        thread_id: UUID of the thread to look up or create.
        enterprise: Caller's enterprise context from JWT.

    Returns:
        The existing or newly created thread dict.

    Raises:
        HTTPException 404 if the thread exists but belongs to another tenant.
    """
    t = await thread_service.get(thread_id)
    if t is None:
        metadata = {"enterprise_id": enterprise.enterprise_id}
        t = await thread_service.create(thread_id, enterprise.enterprise_id, metadata)
    elif t["metadata"].get("enterprise_id") != enterprise.enterprise_id:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


async def _assert_ownership(thread_id: str, enterprise: EnterpriseContext) -> dict:
    """Fetch a thread and verify it belongs to the caller's enterprise.

    Args:
        thread_id: UUID of the thread to look up.
        enterprise: Caller's enterprise context from JWT.

    Returns:
        The thread dict if found and owned by this enterprise.

    Raises:
        HTTPException 404 if the thread doesn't exist or belongs to another tenant.
    """
    t = await thread_service.get(thread_id)
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    if t["metadata"].get("enterprise_id") != enterprise.enterprise_id:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


async def create_thread(
    data: ThreadCreate, enterprise: EnterpriseContext
) -> ThreadResponse:
    """Create a new thread, or return the existing one if ``if_exists=do_nothing``.

    Args:
        data: ThreadCreate schema with optional thread_id, metadata, and if_exists policy.
        enterprise: Caller's enterprise context from JWT.

    Returns:
        ThreadResponse for the created (or existing) thread.

    Raises:
        HTTPException 409 if the thread already exists and ``if_exists`` is not ``do_nothing``.
    """
    thread_id = data.thread_id or str(uuid4())

    existing = await thread_service.get(thread_id)
    if existing:
        if data.if_exists == "do_nothing":
            return _to_response(existing)
        raise HTTPException(status_code=409, detail="Thread already exists")

    metadata = dict(data.metadata or {})
    metadata["enterprise_id"] = enterprise.enterprise_id

    t = await thread_service.create(thread_id, enterprise.enterprise_id, metadata)
    return _to_response(t)


async def search_threads(
    data: ThreadSearch, enterprise: EnterpriseContext
) -> list[ThreadResponse]:
    """Return threads for the caller's enterprise matching the search criteria.

    Args:
        data: ThreadSearch schema with optional status, metadata filters, and pagination.
        enterprise: Caller's enterprise context from JWT.

    Returns:
        List of ThreadResponse objects ordered by updated_at descending.
    """
    results = await thread_service.search(
        enterprise_id=enterprise.enterprise_id,
        metadata=data.metadata,
        status=data.status,
        limit=data.limit,
        offset=data.offset,
    )
    return [_to_response(t) for t in results]


async def get_thread(
    thread_id: str, enterprise: EnterpriseContext
) -> ThreadResponse:
    """Fetch a single thread, verifying enterprise ownership.

    Args:
        thread_id: UUID of the thread to retrieve.
        enterprise: Caller's enterprise context from JWT.

    Returns:
        ThreadResponse for the requested thread.

    Raises:
        HTTPException 404 if the thread doesn't exist or is owned by another tenant.
    """
    return _to_response(await _assert_ownership(thread_id, enterprise))


async def update_thread(
    thread_id: str, data: ThreadUpdate, enterprise: EnterpriseContext
) -> ThreadResponse:
    """Merge new metadata into an existing thread.

    Args:
        thread_id: UUID of the thread to update.
        data: ThreadUpdate schema with the metadata dict to merge.
        enterprise: Caller's enterprise context from JWT.

    Returns:
        Updated ThreadResponse.

    Raises:
        HTTPException 404 if the thread doesn't exist or is owned by another tenant.
    """
    await _assert_ownership(thread_id, enterprise)
    t = await thread_service.update(thread_id, data.metadata)
    return _to_response(t)


async def delete_thread(thread_id: str, enterprise: EnterpriseContext) -> None:
    """Delete a thread after verifying ownership.

    Args:
        thread_id: UUID of the thread to delete.
        enterprise: Caller's enterprise context from JWT.

    Returns:
        None.

    Raises:
        HTTPException 404 if the thread doesn't exist or is owned by another tenant.
    """
    await _assert_ownership(thread_id, enterprise)
    await thread_service.delete(thread_id)
