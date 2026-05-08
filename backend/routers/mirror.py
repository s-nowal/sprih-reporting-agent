"""Per-thread Drive folder linkage.

Three endpoints under ``/threads/{tid}/mirror``:

* ``GET`` → current link state + Drive-side health check.
* ``PUT`` → link (or re-link a broken mapping) the thread to a folder
  with the supplied display name. New folder is created on the
  provider every time — we don't try to dedupe by name.
* ``DELETE`` → drop the mapping. Provider folder is intentionally
  left in place; the user manages it directly in their drive.

By design, threads start unlinked. Sync only happens once the user
opts in via ``PUT``.
"""

from fastapi import APIRouter, Depends, Response

from backend.handlers import mirror_handler
from backend.schemas.mirror import (
    LinkMirrorRequest,
    MirrorLinkResponse,
    MirrorStatusResponse,
)
from backend.security.auth import EnterpriseContext, get_enterprise_context

router = APIRouter(tags=["mirror"])


@router.get(
    "/threads/{thread_id}/mirror",
    response_model=MirrorStatusResponse,
)
async def get_status(
    thread_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """Return current linkage state, including a broken-link flag."""
    return await mirror_handler.get_status(thread_id, enterprise)


@router.put(
    "/threads/{thread_id}/mirror",
    response_model=MirrorLinkResponse,
    status_code=201,
)
async def link(
    thread_id: str,
    body: LinkMirrorRequest,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """Create a provider folder named ``body.folder_name`` and link it."""
    return await mirror_handler.link(thread_id, body, enterprise)


@router.delete(
    "/threads/{thread_id}/mirror",
    status_code=204,
)
async def unlink(
    thread_id: str,
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """Drop the mapping. Provider folder is left in place."""
    await mirror_handler.unlink(thread_id, enterprise)
    return Response(status_code=204)
