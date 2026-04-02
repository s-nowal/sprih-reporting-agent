"""Document upload/listing handler with in-memory stub."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from backend.schemas.documents import DocumentResponse, DocumentUploadResponse
from backend.security.auth import EnterpriseContext

_documents: dict[str, dict] = {}


async def upload_documents(
    files: list[UploadFile], enterprise: EnterpriseContext
) -> list[DocumentUploadResponse]:
    results = []
    now = datetime.now(timezone.utc)
    for f in files:
        doc_id = str(uuid4())
        ext = (f.filename or "").rsplit(".", 1)[-1].lower()
        source_type = {
            "pdf": "pdf",
            "xlsx": "excel",
            "xls": "excel",
            "csv": "excel",
            "docx": "doc",
            "doc": "doc",
            "html": "html",
            "txt": "txt",
        }.get(ext, "unknown")

        doc = {
            "id": doc_id,
            "enterprise_id": enterprise.enterprise_id,
            "entity_id": None,
            "source_type": source_type,
            "source_ref": f.filename or "unnamed",
            "s3_bronze_path": f"enterprise/{enterprise.enterprise_id}/bronze/uploads/{doc_id}/{f.filename}",
            "s3_silver_path": None,
            "status": "fetched",
            "fetched_at": now,
            "created_at": now,
            "metadata": {"content_type": f.content_type, "size": f.size},
        }
        _documents[doc_id] = doc
        results.append(DocumentUploadResponse(**doc))
    return results


async def list_documents(
    enterprise: EnterpriseContext, limit: int = 50, offset: int = 0
) -> list[DocumentResponse]:
    docs = [
        d
        for d in _documents.values()
        if d["enterprise_id"] == enterprise.enterprise_id
    ]
    docs.sort(key=lambda x: x["created_at"], reverse=True)
    return [DocumentResponse(**d) for d in docs[offset : offset + limit]]


async def get_document(
    document_id: str, enterprise: EnterpriseContext
) -> DocumentResponse:
    doc = _documents.get(document_id)
    if not doc or doc["enterprise_id"] != enterprise.enterprise_id:
        raise HTTPException(status_code=404, detail="Document not found")
    return DocumentResponse(**doc)
