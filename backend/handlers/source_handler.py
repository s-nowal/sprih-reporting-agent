"""Source document upload/listing handler with in-memory stub."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from backend.schemas.sources import SourceResponse, SourceUploadResponse
from backend.security.auth import EnterpriseContext

_sources: dict[str, dict] = {}


async def upload_sources(
    files: list[UploadFile], enterprise: EnterpriseContext
) -> list[SourceUploadResponse]:
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
        _sources[doc_id] = doc
        results.append(SourceUploadResponse(**doc))
    return results


async def list_sources(
    enterprise: EnterpriseContext, limit: int = 50, offset: int = 0
) -> list[SourceResponse]:
    docs = [
        d
        for d in _sources.values()
        if d["enterprise_id"] == enterprise.enterprise_id
    ]
    docs.sort(key=lambda x: x["created_at"], reverse=True)
    return [SourceResponse(**d) for d in docs[offset : offset + limit]]


async def get_source(
    source_id: str, enterprise: EnterpriseContext
) -> SourceResponse:
    doc = _sources.get(source_id)
    if not doc or doc["enterprise_id"] != enterprise.enterprise_id:
        raise HTTPException(status_code=404, detail="Source not found")
    return SourceResponse(**doc)
