"""Source document upload and listing endpoints."""

from fastapi import APIRouter, Depends, Query, UploadFile

from backend.handlers import source_handler
from backend.schemas.sources import SourceResponse, SourceUploadResponse
from backend.security.auth import EnterpriseContext, get_enterprise_context

router = APIRouter(tags=["sources"])


@router.post(
    "/sources/upload",
    response_model=list[SourceUploadResponse],
    status_code=201,
)
async def upload_sources(
    files: list[UploadFile],
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await source_handler.upload_sources(files, enterprise)


@router.get("/sources", response_model=list[SourceResponse])
async def list_sources(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await source_handler.list_sources(enterprise, limit, offset)


@router.get("/sources/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await source_handler.get_source(source_id, enterprise)


# --- Readable aliases ---

router.add_api_route(
    "/sources/all", list_sources, methods=["GET"], include_in_schema=False
)
