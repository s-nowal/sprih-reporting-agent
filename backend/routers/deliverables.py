"""Deliverable listing and download endpoints."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from backend.handlers import deliverable_handler
from backend.schemas.deliverables import DeliverableResponse
from backend.security.auth import EnterpriseContext, get_enterprise_context

router = APIRouter(tags=["deliverables"])


@router.get("/deliverables", response_model=list[DeliverableResponse])
async def list_deliverables(
    thread_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await deliverable_handler.list_deliverables(
        enterprise, thread_id, limit, offset
    )


@router.get("/deliverables/{deliverable_id}", response_model=DeliverableResponse)
async def get_deliverable(
    deliverable_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await deliverable_handler.get_deliverable(deliverable_id, enterprise)


@router.get("/deliverables/{deliverable_id}/download")
async def download_deliverable(
    deliverable_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    content = await deliverable_handler.download_deliverable(
        deliverable_id, enterprise
    )
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={deliverable_id}"},
    )


# --- Readable aliases ---

router.add_api_route(
    "/deliverables/all", list_deliverables, methods=["GET"], include_in_schema=False
)
