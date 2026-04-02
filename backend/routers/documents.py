"""Data source upload and listing endpoints."""

from fastapi import APIRouter, Depends, Query, UploadFile

from backend.handlers import document_handler
from backend.schemas.documents import DocumentResponse, DocumentUploadResponse
from backend.security.auth import EnterpriseContext, get_enterprise_context

router = APIRouter(tags=["data_sources"])


@router.post(
    "/data_sources/upload",
    response_model=list[DocumentUploadResponse],
    status_code=201,
)
async def upload_documents(
    files: list[UploadFile],
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await document_handler.upload_documents(files, enterprise)


@router.get("/data_sources", response_model=list[DocumentResponse])
async def list_documents(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await document_handler.list_documents(enterprise, limit, offset)


@router.get("/data_sources/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await document_handler.get_document(document_id, enterprise)


# --- Readable aliases ---

router.add_api_route(
    "/data_sources/all", list_documents, methods=["GET"], include_in_schema=False
)
