"""Drive sync service — reconciles S3 and Google Drive at thread-turn boundaries.

The sync runs at S3 boundaries (not workspace temp-dir boundaries):

    sync_in    →    workspace_service.checkout    →    agent run
                                                          │
    workspace_service.commit    ←──────────────────────────┘
        │
        ▼
    sync_out

After ``sync_in`` the S3 prefix for the thread holds the latest user-edited
files, which ``checkout`` then copies into the temp workspace. After
``commit`` the S3 prefix holds the agent's writes, which ``sync_out`` mirrors
to Drive.

Mirror policy is per-agent (``settings.drive_mirror_subdirs``) — for the
reporting agent, only ``input/`` and ``output/`` mirror to Drive. ``workspace/``
and ``reference/`` stay S3-only.

Conflict policy: latest ``modifiedTime`` wins. The user's stated assumption
is that the agent and the user never edit at the same time, so this reduces
to a simple "newer side wins" rule.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import random
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select

from backend.config import settings
from backend.infra.google_drive import (
    GoogleDriveClient,
    credentials_from_refresh_token,
)
from backend.infra.registry import get_db, get_storage
from backend.models.google_credentials import GoogleCredentials
from backend.models.thread_drive_mapping import ThreadDriveMapping

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Random thread-title generator
# ---------------------------------------------------------------------------

_ADJECTIVES = [
    "amber", "azure", "brisk", "bronze", "calm", "cedar", "cobalt", "coral",
    "crimson", "dewy", "ember", "frost", "golden", "hazel", "indigo", "jade",
    "lemon", "lunar", "mossy", "nimble", "olive", "opal", "pearl", "plum",
    "quiet", "rust", "saffron", "silken", "slate", "sunny", "teal", "violet",
    "willow", "zen",
]
_NOUNS = [
    "atlas", "beacon", "breeze", "brook", "canyon", "comet", "delta", "ember",
    "ferry", "field", "forest", "garden", "harbor", "horizon", "island",
    "lagoon", "ledger", "lighthouse", "meadow", "mosaic", "mountain", "orbit",
    "prairie", "reef", "ridge", "river", "sapling", "summit", "thicket",
    "trail", "tundra", "valley", "voyage", "willow",
]


def generate_thread_title() -> str:
    """Generate a memorable random thread title used as a Drive folder name.

    Format is ``"{adjective}-{noun}-{nnn}"`` (e.g. ``"saffron-meadow-274"``).
    Three-digit suffix avoids collisions across threads with the same word
    pair without being long enough to be ugly.

    Returns:
        A 3-component slug suitable as a folder name.
    """
    return (
        f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}-"
        f"{random.randint(100, 999)}"
    )


# ---------------------------------------------------------------------------
# Credential / client helpers
# ---------------------------------------------------------------------------


async def _load_credentials(enterprise_id: str) -> GoogleCredentials | None:
    """Fetch the GoogleCredentials row for an enterprise, or ``None``.

    Args:
        enterprise_id: Tenant identifier.

    Returns:
        The ORM row if the enterprise has connected Drive, else ``None``.
    """
    db = get_db()
    async with db() as session:
        return await session.get(GoogleCredentials, enterprise_id)


def _build_client(creds_row: GoogleCredentials) -> GoogleDriveClient:
    """Construct a ``GoogleDriveClient`` from a stored credentials row.

    Args:
        creds_row: The ``GoogleCredentials`` ORM row.

    Returns:
        A blocking Drive client ready to be used inside ``asyncio.to_thread``.
    """
    creds = credentials_from_refresh_token(
        refresh_token=creds_row.refresh_token,
        scopes=creds_row.scopes.split() if creds_row.scopes else None,
    )
    return GoogleDriveClient(creds)


# ---------------------------------------------------------------------------
# S3 helpers (operate on the LocalStorage adapter's filesystem-rooted layout)
# ---------------------------------------------------------------------------


def _s3_workspace_prefix(enterprise_id: str, thread_id: str) -> str:
    """Mirror of workspace_service._s3_workspace_prefix to keep them aligned."""
    return f"enterprise/{enterprise_id}/workspaces/{thread_id}"


def _s3_subdir_root(enterprise_id: str, thread_id: str, subdir: str) -> Path:
    """Absolute filesystem path of an S3 subdirectory for a thread.

    Args:
        enterprise_id: Tenant id.
        thread_id: Thread id.
        subdir: One of the workspace subdirs (``"input"``, ``"output"`` etc.).

    Returns:
        Absolute path under the LocalStorage root. May not exist yet.
    """
    storage = get_storage()
    return Path(storage.abs_path(f"{_s3_workspace_prefix(enterprise_id, thread_id)}/{subdir}"))


# ---------------------------------------------------------------------------
# Mapping CRUD
# ---------------------------------------------------------------------------


async def _get_mapping(thread_id: str) -> ThreadDriveMapping | None:
    """Fetch the ThreadDriveMapping row for a thread.

    Args:
        thread_id: Thread id.

    Returns:
        The ORM row or ``None``.
    """
    db = get_db()
    async with db() as session:
        return await session.get(ThreadDriveMapping, thread_id)


async def _upsert_mapping(
    thread_id: str,
    enterprise_id: str,
    agent_name: str,
    thread_title: str,
    drive_folder_id: str,
) -> ThreadDriveMapping:
    """Insert or update a ThreadDriveMapping row.

    Args:
        thread_id: Thread id (PK).
        enterprise_id: Tenant id.
        agent_name: Graph name.
        thread_title: Display name used for the Drive folder.
        drive_folder_id: Drive folder ID for the per-thread folder.

    Returns:
        The committed ORM row.
    """
    db = get_db()
    async with db() as session:
        existing = await session.get(ThreadDriveMapping, thread_id)
        if existing is None:
            row = ThreadDriveMapping(
                thread_id=thread_id,
                enterprise_id=enterprise_id,
                agent_name=agent_name,
                thread_title=thread_title,
                drive_folder_id=drive_folder_id,
                last_synced_at=None,
            )
            session.add(row)
        else:
            existing.thread_title = thread_title
            existing.drive_folder_id = drive_folder_id
            row = existing
        await session.commit()
        await session.refresh(row)
        return row


async def _set_last_synced(thread_id: str, when: datetime) -> None:
    """Update the ``last_synced_at`` timestamp for a thread mapping.

    Args:
        thread_id: Thread id.
        when: Timestamp to record.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(ThreadDriveMapping, thread_id)
        if row is None:
            return
        row.last_synced_at = when
        await session.commit()


# ---------------------------------------------------------------------------
# Folder bootstrap
# ---------------------------------------------------------------------------


async def setup_thread_folder(
    enterprise_id: str,
    thread_id: str,
    agent_name: str,
) -> ThreadDriveMapping | None:
    """Ensure the per-thread Drive folder structure exists, creating as needed.

    Folder layout produced::

        Sprih/
            {agent_name}/
                {thread_title}/
                    input/
                    output/
                    ...mirrored subdirs from settings.drive_mirror_subdirs...

    The agent-name folder and per-thread folder are created lazily and the
    resulting Drive folder ID is persisted in ``thread_drive_mappings``.
    Subsequent calls are no-ops if the mapping already exists.

    Args:
        enterprise_id: Tenant id (used to look up credentials and parent folder).
        thread_id: Thread id.
        agent_name: Graph name (becomes a subfolder under the parent).

    Returns:
        The ``ThreadDriveMapping`` row, or ``None`` if the enterprise has not
        connected Drive yet (the sync becomes a no-op).
    """
    creds_row = await _load_credentials(enterprise_id)
    if creds_row is None or not creds_row.drive_parent_folder_id:
        return None

    existing = await _get_mapping(thread_id)
    if existing is not None:
        return existing

    title = generate_thread_title()
    parent_folder_id = creds_row.drive_parent_folder_id
    mirror_subdirs = settings.drive_mirror_subdirs.get(agent_name, [])

    def _build() -> str:
        client = _build_client(creds_row)
        # Sprih / {agent_name} / {thread_title}
        agent_folder_id = client.find_or_create_folder(parent_folder_id, agent_name)
        thread_folder_id = client.create_folder(agent_folder_id, title)
        # Pre-create mirrored subdirs so the user sees the expected layout
        # immediately after sync, even before any files exist.
        for subdir in mirror_subdirs:
            client.find_or_create_folder(thread_folder_id, subdir)
        return thread_folder_id

    drive_folder_id = await asyncio.to_thread(_build)

    mapping = await _upsert_mapping(
        thread_id=thread_id,
        enterprise_id=enterprise_id,
        agent_name=agent_name,
        thread_title=title,
        drive_folder_id=drive_folder_id,
    )
    logger.info(
        "Provisioned Drive folder %s for thread %s (title=%r) under %s/%s",
        drive_folder_id,
        thread_id,
        title,
        agent_name,
        title,
    )
    return mapping


# ---------------------------------------------------------------------------
# Sync in / out
# ---------------------------------------------------------------------------


def _mirror_subdirs_for(agent_name: str) -> list[str]:
    """Return the subdir mirror list configured for an agent."""
    return settings.drive_mirror_subdirs.get(agent_name, [])


def _is_native_google_doc(mime_type: str) -> bool:
    """``True`` for ``application/vnd.google-apps.*`` mime types we never sync."""
    return mime_type.startswith("application/vnd.google-apps.")


def _guess_mime_type(name: str) -> str:
    """Best-effort MIME type guess for a filename.

    Falls back to ``application/octet-stream`` so an unknown extension still
    uploads cleanly.

    Args:
        name: File basename or path.

    Returns:
        A MIME type string.
    """
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


async def sync_in(
    enterprise_id: str,
    thread_id: str,
    agent_name: str,
) -> int:
    """Pull user-edited files from Drive into S3 (Drive → S3).

    For each mirrored subdir, walks the Drive folder and downloads any file
    whose ``modifiedTime`` is newer than ``last_synced_at`` (or any file at
    all on the very first sync). Native Google Docs are skipped.

    Args:
        enterprise_id: Tenant id.
        thread_id: Thread id.
        agent_name: Graph name (decides mirror policy).

    Returns:
        Number of files pulled. ``0`` if Drive isn't connected for this
        enterprise or no mapping exists yet.
    """
    mapping = await _get_mapping(thread_id)
    if mapping is None:
        return 0
    creds_row = await _load_credentials(enterprise_id)
    if creds_row is None:
        return 0

    mirror_subdirs = _mirror_subdirs_for(agent_name)
    if not mirror_subdirs:
        return 0

    cutoff = mapping.last_synced_at  # may be None

    def _do_sync() -> int:
        client = _build_client(creds_row)
        pulled = 0
        for subdir in mirror_subdirs:
            subdir_id = client.find_or_create_folder(mapping.drive_folder_id, subdir)
            files = client.list_files_recursive(subdir_id)
            for f in files:
                if _is_native_google_doc(f["mimeType"]):
                    logger.info(
                        "Skipping native Google Doc %s (%s)",
                        f["relative_path"], f["mimeType"],
                    )
                    continue
                modified = client.parse_modified_time(f["modifiedTime"])
                if cutoff is not None and modified is not None and modified <= cutoff:
                    continue
                content = client.download_file(f["id"])
                # S3 path mirrors workspace layout: <prefix>/<subdir>/<rel_path>
                s3_key = (
                    f"{_s3_workspace_prefix(enterprise_id, thread_id)}/"
                    f"{subdir}/{f['relative_path']}"
                )
                get_storage().write(s3_key, content)
                pulled += 1
                logger.info(
                    "sync_in: pulled %s/%s (%s bytes)",
                    subdir, f["relative_path"], len(content),
                )
        return pulled

    return await asyncio.to_thread(_do_sync)


async def sync_out(
    enterprise_id: str,
    thread_id: str,
    agent_name: str,
) -> int:
    """Push agent-written files from S3 to Drive (S3 → Drive).

    Walks each mirrored S3 subdir and uploads files whose mtime is newer
    than ``last_synced_at`` (or every file on the first sync). Updates
    ``last_synced_at`` to the current time on success.

    For each S3 file we look up the matching Drive file by relative path. If
    one exists we update its content (preserving the Drive ``fileId``); if
    not we create a new file. Subfolders are created on demand.

    Args:
        enterprise_id: Tenant id.
        thread_id: Thread id.
        agent_name: Graph name.

    Returns:
        Number of files pushed. ``0`` if Drive isn't connected.
    """
    mapping = await _get_mapping(thread_id)
    if mapping is None:
        return 0
    creds_row = await _load_credentials(enterprise_id)
    if creds_row is None:
        return 0

    mirror_subdirs = _mirror_subdirs_for(agent_name)
    if not mirror_subdirs:
        return 0

    cutoff = mapping.last_synced_at  # may be None

    def _do_sync() -> int:
        client = _build_client(creds_row)
        pushed = 0
        for subdir in mirror_subdirs:
            local_root = _s3_subdir_root(enterprise_id, thread_id, subdir)
            if not local_root.exists():
                continue
            subdir_id = client.find_or_create_folder(mapping.drive_folder_id, subdir)
            # Index existing Drive contents once per subdir for fileId lookup.
            existing = client.list_files_recursive(subdir_id)
            by_path: dict[str, dict[str, Any]] = {f["relative_path"]: f for f in existing}

            for src in sorted(local_root.rglob("*")):
                if not src.is_file():
                    continue
                rel = src.relative_to(local_root).as_posix()
                if cutoff is not None:
                    mtime = datetime.utcfromtimestamp(src.stat().st_mtime)
                    if mtime <= cutoff:
                        continue
                content = src.read_bytes()
                mime = _guess_mime_type(src.name)

                drive_match = by_path.get(rel)
                if drive_match:
                    client.update_file_content(
                        drive_match["id"], content, mime
                    )
                else:
                    # Walk/create intermediate folders, then upload.
                    parent_id = subdir_id
                    parts = rel.split("/")
                    for part in parts[:-1]:
                        parent_id = client.find_or_create_folder(parent_id, part)
                    client.upload_new_file(
                        parent_id=parent_id,
                        name=parts[-1],
                        content=content,
                        mime_type=mime,
                    )
                pushed += 1
                logger.info(
                    "sync_out: pushed %s/%s (%s bytes)", subdir, rel, len(content)
                )
        return pushed

    pushed = await asyncio.to_thread(_do_sync)
    # Record the timestamp *after* uploads complete so that a subsequent
    # sync_in does not re-pull files we just pushed (Drive's modifiedTime
    # reflects the upload moment, which is necessarily before "now").
    await _set_last_synced(thread_id, datetime.utcnow())
    return pushed


# ---------------------------------------------------------------------------
# OAuth-side helper (used by the auth router)
# ---------------------------------------------------------------------------


async def store_credentials(
    enterprise_id: str,
    refresh_token: str,
    agent_email: str,
    scopes: list[str],
    drive_parent_folder_id: str | None,
) -> None:
    """Insert or update the ``GoogleCredentials`` row for an enterprise.

    Called from the OAuth callback handler once a refresh token has been
    obtained from Google.

    Args:
        enterprise_id: Tenant id.
        refresh_token: Long-lived OAuth refresh token.
        agent_email: Email of the account that authorised the app.
        scopes: List of OAuth scopes the token was issued with.
        drive_parent_folder_id: Drive folder id of the shared "Sprih" folder,
            if known. May be ``None`` and provided later via a separate
            settings call.
    """
    db = get_db()
    async with db() as session:
        existing = await session.get(GoogleCredentials, enterprise_id)
        if existing is None:
            row = GoogleCredentials(
                enterprise_id=enterprise_id,
                agent_email=agent_email,
                refresh_token=refresh_token,
                scopes=" ".join(scopes),
                drive_parent_folder_id=drive_parent_folder_id,
            )
            session.add(row)
        else:
            existing.refresh_token = refresh_token
            existing.agent_email = agent_email
            existing.scopes = " ".join(scopes)
            if drive_parent_folder_id is not None:
                existing.drive_parent_folder_id = drive_parent_folder_id
        await session.commit()


async def set_parent_folder(enterprise_id: str, drive_parent_folder_id: str) -> bool:
    """Update only the ``drive_parent_folder_id`` for an enterprise.

    Args:
        enterprise_id: Tenant id.
        drive_parent_folder_id: Drive folder id of the shared "Sprih" folder.

    Returns:
        ``True`` if the row was updated, ``False`` if no credentials row
        exists for that enterprise yet.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(GoogleCredentials, enterprise_id)
        if row is None:
            return False
        row.drive_parent_folder_id = drive_parent_folder_id
        await session.commit()
        return True


async def get_status(enterprise_id: str) -> dict[str, Any]:
    """Return a small status dict describing the enterprise's Drive integration.

    Useful for the dev-time ``GET /auth/google/status`` endpoint and for any
    future admin UI.

    Args:
        enterprise_id: Tenant id.

    Returns:
        Dict with ``connected`` (bool), ``agent_email`` (str|None), and
        ``drive_parent_folder_id`` (str|None). Never raises.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(GoogleCredentials, enterprise_id)
        if row is None:
            return {
                "connected": False,
                "agent_email": None,
                "drive_parent_folder_id": None,
            }
        return {
            "connected": True,
            "agent_email": row.agent_email,
            "drive_parent_folder_id": row.drive_parent_folder_id,
        }
