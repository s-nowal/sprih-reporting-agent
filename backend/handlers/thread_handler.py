"""Thread CRUD handler with in-memory stub store."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from backend.schemas.threads import (
    ThreadCreate,
    ThreadResponse,
    ThreadSearch,
    ThreadUpdate,
)
from backend.security.auth import EnterpriseContext

# In-memory store — replaced by ThreadService + DB later
_threads: dict[str, dict] = {}


def _to_response(t: dict) -> ThreadResponse:
    return ThreadResponse(**t)


def _assert_ownership(thread_id: str, enterprise: EnterpriseContext) -> dict:
    t = _threads.get(thread_id)
    if not t:
        raise HTTPException(status_code=404, detail="Thread not found")
    if t["metadata"].get("enterprise_id") != enterprise.enterprise_id:
        raise HTTPException(status_code=404, detail="Thread not found")
    return t


async def create_thread(
    data: ThreadCreate, enterprise: EnterpriseContext
) -> ThreadResponse:
    thread_id = data.thread_id or str(uuid4())

    if thread_id in _threads:
        if data.if_exists == "do_nothing":
            return _to_response(_threads[thread_id])
        raise HTTPException(status_code=409, detail="Thread already exists")

    now = datetime.now(timezone.utc)
    metadata = data.metadata or {}
    metadata["enterprise_id"] = enterprise.enterprise_id

    t = {
        "thread_id": thread_id,
        "created_at": now,
        "updated_at": now,
        "metadata": metadata,
        "status": "idle",
        "values": {},
        "interrupts": {},
    }
    _threads[thread_id] = t
    return _to_response(t)


async def search_threads(
    data: ThreadSearch, enterprise: EnterpriseContext
) -> list[ThreadResponse]:
    results = []
    for t in _threads.values():
        if t["metadata"].get("enterprise_id") != enterprise.enterprise_id:
            continue
        if data.status and t["status"] != data.status:
            continue
        if data.metadata:
            if not all(t["metadata"].get(k) == v for k, v in data.metadata.items()):
                continue
        results.append(t)

    results.sort(key=lambda x: x["updated_at"], reverse=True)
    return [_to_response(t) for t in results[data.offset : data.offset + data.limit]]


async def get_thread(
    thread_id: str, enterprise: EnterpriseContext
) -> ThreadResponse:
    return _to_response(_assert_ownership(thread_id, enterprise))


async def update_thread(
    thread_id: str, data: ThreadUpdate, enterprise: EnterpriseContext
) -> ThreadResponse:
    t = _assert_ownership(thread_id, enterprise)
    t["metadata"].update(data.metadata)
    t["updated_at"] = datetime.now(timezone.utc)
    return _to_response(t)


async def delete_thread(thread_id: str, enterprise: EnterpriseContext) -> None:
    _assert_ownership(thread_id, enterprise)
    del _threads[thread_id]
