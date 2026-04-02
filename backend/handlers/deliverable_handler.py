"""Deliverable listing/download handler with in-memory stub."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from backend.schemas.deliverables import DeliverableResponse
from backend.security.auth import EnterpriseContext

_deliverables: dict[str, dict] = {}


async def list_deliverables(
    enterprise: EnterpriseContext,
    thread_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[DeliverableResponse]:
    results = [
        d
        for d in _deliverables.values()
        if d["enterprise_id"] == enterprise.enterprise_id
        and (thread_id is None or d.get("thread_id") == thread_id)
    ]
    results.sort(key=lambda x: x["created_at"], reverse=True)
    return [DeliverableResponse(**d) for d in results[offset : offset + limit]]


async def get_deliverable(
    deliverable_id: str, enterprise: EnterpriseContext
) -> DeliverableResponse:
    d = _deliverables.get(deliverable_id)
    if not d or d["enterprise_id"] != enterprise.enterprise_id:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return DeliverableResponse(**d)


async def download_deliverable(
    deliverable_id: str, enterprise: EnterpriseContext
) -> bytes:
    """Returns file bytes. Stub returns placeholder text."""
    d = _deliverables.get(deliverable_id)
    if not d or d["enterprise_id"] != enterprise.enterprise_id:
        raise HTTPException(status_code=404, detail="Deliverable not found")
    return b"Placeholder deliverable content. Agent execution not wired yet."
