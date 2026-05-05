from fastapi import APIRouter, Depends, UploadFile, File

from backend.security.auth import EnterpriseContext, get_enterprise_context
from backend.sync.doc_sync import wait_for_sync, fulfill_sync, _sync_events
from backend.handlers import documents_handler
from pydantic import BaseModel
from typing import Optional
import base64

router = APIRouter(tags=["documents"])

class WordAddinPayload(BaseModel):
    filename: Optional[str] = "output.md"
    filepath: Optional[str] = "output"
    document_base64: Optional[str] = None
    document_text: Optional[str] = None

@router.post("/documents/upload")
async def upload(
    file: UploadFile,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await documents_handler.upload_document(file, enterprise)

@router.post("/documents/upload-from-addin")
async def upload_from_addin(
    payload: WordAddinPayload,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await documents_handler.upload_document_from_addin(payload, enterprise)

@router.get("/documents/upload-from-addin")
async def get_from_addin(
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await documents_handler.get_document_from_addin(enterprise)

@router.get("/documents/{document_id}")
async def get_doc(
    document_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await documents_handler.get_document(document_id, enterprise)

@router.get("/documents/{document_id}/read")
async def read_doc(
    document_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await documents_handler.read_document(document_id, enterprise)

# @router.get("/documents/sync-requested/{thread_id}")
# async def check_sync_requested(
#     thread_id: str,
#     enterprise=Depends(get_enterprise_context)
# ):
#     event = _sync_events.get(thread_id)
#     return {"requested": event is not None and not event.is_set()}


# @router.post("/documents/sync-fulfill/{thread_id}")
# async def fulfill_doc_sync(
#     thread_id: str,
#     file: UploadFile = File(...),
#     enterprise=Depends(get_enterprise_context)
# ):
#     print("[sync] fulfill endpoint hit")
#     result = await documents_handler.upload_document(file, enterprise)
#     document_id = result.get("document_id")
#     doc_content = documents_handler._document_content.get(document_id, "")

#     fulfill_sync(thread_id, {
#         "content": doc_content,
#         "document_id": document_id
#     })

#     return {"document_id": document_id}