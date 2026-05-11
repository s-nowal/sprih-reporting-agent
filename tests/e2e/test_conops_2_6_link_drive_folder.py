"""E2E test for ConOps §2.6 — Link thread to a brand-new Drive folder.

Spec source: ``docs/ConOps.md`` §2.6.

Drives ``PUT /threads/{tid}/mirror`` with a folder name against the **real**
Google Drive backend (using sprih's existing refresh token, copied onto
``test-enterprise`` by the ``real_mirror_credentials`` fixture). Verifies the
folder is actually created in Drive AND a ``thread_mirror_mappings`` row
is inserted with the right shape. Folder is trashed on teardown.

Spec recap:

    Trigger: Sara types a folder name and saves in the edit-thread panel.

    API call:
      - PUT /threads/{thread_id}/mirror
        body: {provider: "google_drive", folder_name: "<name>"}
        Response: {provider, folder_id, folder_name}

    Writes:
      Drive (external) — create a new folder under
        mirror_credentials.parent_folder_id; the response carries the new id.
      thread_mirror_mappings — INSERT row with thread_id, provider, folder_id,
        folder_name, last_synced_at=NULL.

Requires:
  - Docker containers running
  - An existing (sprih, google_drive) mirror_credentials row with a valid
    refresh token and parent_folder_id (set up via the OAuth flow in dev).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infra.google_drive import (
    GoogleDriveClient,
    credentials_from_refresh_token,
)
from backend.models.thread_mirror_mapping import ThreadMirrorMapping


async def test_section_2_6_link_brand_new_drive_folder(
    client,
    auth_headers,
    fresh_thread,
    real_mirror_credentials,
    drive_cleanup,
    db_session: AsyncSession,
):
    """Link a fresh thread to a new Drive folder and verify both sides.

    Real Drive call goes out via the existing sprih refresh token. The
    ``drive_cleanup`` fixture trashes the created folder and clears the
    ``thread_mirror_mappings`` row after the test finishes.
    """
    thread_id = fresh_thread["thread_id"]
    folder_name = f"pytest-q3-{uuid.uuid4().hex[:8]}"

    # =========================================================================
    # API call: PUT /threads/{tid}/mirror with a folder name
    # =========================================================================
    resp = client.put(
        f"/threads/{thread_id}/mirror",
        json={"folder_name": folder_name, "agent_name": "reporting-agent"},
        headers=auth_headers,
    )
    assert resp.status_code == 201, (
        f"PUT /mirror returned {resp.status_code}: {resp.text[:300]}"
    )
    body = resp.json()
    assert body["provider"] == "google_drive"
    assert body["folder_name"] == folder_name, (
        f"Spec: response should echo the linked folder name; "
        f"got {body['folder_name']!r} vs {folder_name!r}"
    )
    folder_id = body["folder_id"]
    assert folder_id and isinstance(folder_id, str), (
        f"Spec: response should carry a Drive folder_id; got {folder_id!r}"
    )

    # Register the new folder for trashing on teardown. ``drive_cleanup``
    # walks the tree, so trashing the thread folder also takes care of the
    # ``input/`` and ``output/`` subdirs the link step creates underneath.
    drive_cleanup(folder_id, thread_id=thread_id)

    # =========================================================================
    # DB write: thread_mirror_mappings row inserted
    # =========================================================================
    await db_session.rollback()
    mapping = (
        await db_session.execute(
            select(ThreadMirrorMapping).where(
                ThreadMirrorMapping.thread_id == thread_id
            )
        )
    ).scalar_one_or_none()
    assert mapping is not None, (
        "Spec: thread_mirror_mappings row should be inserted on link"
    )
    assert mapping.provider == "google_drive"
    assert mapping.folder_id == folder_id
    assert mapping.thread_title == folder_name, (
        f"Spec: mapping.thread_title (cached folder name) should match the "
        f"requested folder_name; got {mapping.thread_title!r}"
    )
    # last_synced_at is NULL until the first sync-out completes (§2.8).
    assert mapping.last_synced_at is None, (
        f"Spec: last_synced_at should be NULL until the first sync-out; "
        f"got {mapping.last_synced_at!r}"
    )

    # =========================================================================
    # Drive verification: the folder really exists on Drive
    # =========================================================================
    # Build a Drive client with the same creds the fixture exposed and read
    # the folder metadata back to prove the link step actually created
    # something on Drive.
    creds = credentials_from_refresh_token(
        refresh_token=real_mirror_credentials["refresh_token"],
        scopes=real_mirror_credentials["scopes"].split(),
    )
    client_drive = GoogleDriveClient(creds)
    meta = client_drive._service.files().get(
        fileId=folder_id,
        fields="id,name,mimeType,trashed",
        supportsAllDrives=True,
    ).execute()
    assert meta["id"] == folder_id
    assert meta["name"] == folder_name, (
        f"Spec: Drive folder should be named {folder_name!r}; "
        f"got {meta['name']!r}"
    )
    assert meta["mimeType"] == "application/vnd.google-apps.folder"
    assert not meta.get("trashed", False), (
        "Drive folder should not be trashed immediately after creation"
    )
