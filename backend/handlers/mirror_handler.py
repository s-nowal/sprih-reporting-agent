"""Per-thread mirror linkage orchestration.

Three operations exposed via REST:

* ``get_status`` — is the thread linked? Is the linked folder still
  reachable on the provider, or has it been deleted? Used by the UI
  edit panel to decide which form to render.
* ``link`` — create a provider folder with the user-supplied name and
  store the mapping. Rejects requests that overwrite a healthy
  existing link unless the caller passes ``if_broken=true`` and the
  current link is in fact broken.
* ``unlink`` — drop the mapping. The provider folder is intentionally
  left in place; the user can delete it manually.

The thread row is verified to belong to the caller's enterprise on
every operation.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import HTTPException
from googleapiclient.errors import HttpError as DriveHttpError

from backend.handlers.thread_handler import _assert_ownership
from backend.schemas.mirror import (
    LinkMirrorRequest,
    MirrorLinkResponse,
    MirrorStatusResponse,
)
from backend.security.auth import EnterpriseContext
from backend.services import mirror as mirror_service
from backend.services.mirror.base import (
    _delete_mapping,
    _get_mapping,
)

logger = logging.getLogger(__name__)


async def get_status(
    thread_id: str, enterprise: EnterpriseContext
) -> MirrorStatusResponse:
    """Return the current link state for ``thread_id``.

    On a linked thread, makes one provider-side metadata fetch to
    populate ``folder_name`` and to set ``is_broken=True`` when the
    folder has vanished.

    Raises:
        HTTPException 404 if the thread doesn't belong to the caller.
    """
    await _assert_ownership(thread_id, enterprise)

    mapping = await _get_mapping(thread_id)
    if mapping is None:
        return MirrorStatusResponse(linked=False)

    provider = await mirror_service.get_provider_for(
        enterprise.enterprise_id, mapping.provider
    )
    if provider is None:
        # Mapping points at a provider whose credentials are gone — treat
        # as broken so the UI offers a re-link path.
        return MirrorStatusResponse(
            linked=True,
            provider=mapping.provider,
            folder_id=mapping.folder_id,
            folder_name=mapping.thread_title,
            is_broken=True,
        )

    meta = await asyncio.to_thread(provider.get_folder_metadata, mapping.folder_id)
    if meta is None:
        return MirrorStatusResponse(
            linked=True,
            provider=mapping.provider,
            folder_id=mapping.folder_id,
            folder_name=mapping.thread_title,
            is_broken=True,
        )
    return MirrorStatusResponse(
        linked=True,
        provider=mapping.provider,
        folder_id=mapping.folder_id,
        folder_name=meta.get("name") or mapping.thread_title,
        is_broken=False,
    )


async def link(
    thread_id: str,
    body: LinkMirrorRequest,
    enterprise: EnterpriseContext,
) -> MirrorLinkResponse:
    """Create a provider folder named ``body.folder_name`` and store the mapping.

    Rules:

    * Thread must belong to the caller's enterprise.
    * If the thread is already linked AND the linked folder is healthy,
      reject with 409 (caller must unlink first).
    * If the thread is already linked AND the folder is broken, allow
      re-link only when ``body.if_broken=True``. Otherwise 409.
    * If the enterprise has no provider connected, 412.

    Raises:
        HTTPException 404 (thread not owned) / 409 (link conflict) /
            412 (no provider configured).
    """
    await _assert_ownership(thread_id, enterprise)

    provider = await mirror_service.get_provider(enterprise.enterprise_id)
    if provider is None:
        raise HTTPException(
            status_code=412,
            detail="No mirror provider connected for this enterprise.",
        )

    existing = await _get_mapping(thread_id)
    if existing is not None:
        # Determine if the existing link is healthy or broken.
        meta = await asyncio.to_thread(
            provider.get_folder_metadata, existing.folder_id
        )
        is_broken = meta is None
        if not is_broken:
            raise HTTPException(
                status_code=409,
                detail="Thread is already linked to a healthy folder.",
            )
        if not body.if_broken:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Thread is linked to a broken folder. "
                    "Re-link requires if_broken=true."
                ),
            )
        # Drop the broken mapping so setup_thread_folder will re-create.
        await _delete_mapping(thread_id)

    try:
        thread = await provider.setup_thread_folder(
            enterprise_id=enterprise.enterprise_id,
            thread_id=thread_id,
            agent_name=body.agent_name,
            folder_name=body.folder_name,
        )
    except DriveHttpError as exc:
        if exc.resp.status == 404:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Parent Drive folder not found. "
                    "Check that the folder ID is correct and the account has access."
                ),
            ) from exc
        raise HTTPException(status_code=502, detail=f"Drive API error: {exc.reason}") from exc
    if thread is None:
        # Either the parent folder isn't configured (412 already
        # checked) or the thread row vanished mid-flight.
        raise HTTPException(status_code=409, detail="Could not provision folder.")

    mapping = await _get_mapping(thread_id)
    assert mapping is not None  # setup just wrote it

    # Push any existing workspace files into the freshly created folder so
    # the user sees them immediately without waiting for the next agent run.
    async def _background_sync() -> None:
        try:
            pushed = await provider.sync_out(
                enterprise.enterprise_id, thread_id, body.agent_name
            )
            logger.info("post-link sync_out pushed %d file(s) for thread %s", pushed, thread_id)
        except Exception:
            logger.exception("post-link sync_out failed for thread %s", thread_id)

    asyncio.create_task(_background_sync())

    return MirrorLinkResponse(
        provider=mapping.provider,
        folder_id=mapping.folder_id,
        folder_name=mapping.thread_title or body.folder_name,
    )


async def unlink(thread_id: str, enterprise: EnterpriseContext) -> None:
    """Delete the mapping row. Provider folder is left in place.

    Raises:
        HTTPException 404 if the thread doesn't belong to the caller.
    """
    await _assert_ownership(thread_id, enterprise)
    await _delete_mapping(thread_id)
