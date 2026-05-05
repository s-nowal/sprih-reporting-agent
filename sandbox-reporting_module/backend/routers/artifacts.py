"""Artifact listing and download endpoints."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response

from backend.handlers import artifact_handler
from backend.schemas.artifacts import ArtifactResponse
from backend.security.auth import EnterpriseContext, get_enterprise_context

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts", response_model=list[ArtifactResponse])
async def list_artifacts(
    thread_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await artifact_handler.list_artifacts(
        enterprise, thread_id, limit, offset
    )


@router.get("/artifacts/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    artifact_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    return await artifact_handler.get_artifact(artifact_id, enterprise)


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    content = await artifact_handler.download_artifact(
        artifact_id, enterprise
    )
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={artifact_id}"},
    )


# --- Readable aliases ---

router.add_api_route(
    "/artifacts/all", list_artifacts, methods=["GET"], include_in_schema=False
)
