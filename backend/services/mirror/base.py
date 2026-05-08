"""``MirrorProvider`` base class — provider-agnostic sync orchestration.

Concrete subclasses implement a small set of provider primitives
(folder CRUD, listing, download, upload, modified-time parsing). The
base class composes those primitives into the ``setup_thread_folder``,
``sync_in``, and ``sync_out`` operations that the run handler calls.

The split keeps anything that talks to a specific cloud (Google Drive,
Microsoft Graph, ...) out of the orchestration layer, so adding a new
provider only requires implementing the abstract methods below.
"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
import random
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.config import settings
from backend.infra.registry import get_db, get_storage
from backend.models.mirror_credentials import MirrorCredentials
from backend.models.thread import Thread
from backend.models.thread_mirror_mapping import ThreadMirrorMapping
from backend.services.agent.workspace import workspace_prefix as _s3_workspace_prefix

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Random thread-title generator (provider-agnostic)
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
    """Generate a memorable random thread title used as a folder name.

    Format is ``"{adjective}-{noun}-{nnn}"`` (e.g. ``"saffron-meadow-274"``).
    Three-digit suffix avoids collisions across threads with the same word
    pair without becoming visually noisy.

    Returns:
        A 3-component slug suitable for use as a folder name.
    """
    return (
        f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}-"
        f"{random.randint(100, 999)}"
    )


# ---------------------------------------------------------------------------
# S3-side helpers
# ---------------------------------------------------------------------------


def _s3_subdir_root(enterprise_id: str, thread_id: str, subdir: str) -> Path:
    """Absolute filesystem path of an S3 subdirectory for a thread.

    Args:
        enterprise_id: Tenant id.
        thread_id: Thread id.
        subdir: Workspace subdir (``"input"``, ``"output"`` etc.).

    Returns:
        Absolute path under the LocalStorage root. May not exist yet.
    """
    storage = get_storage()
    return Path(
        storage.abs_path(
            f"{_s3_workspace_prefix(enterprise_id, thread_id)}/{subdir}"
        )
    )


def _mirror_subdirs_for(agent_name: str) -> list[str]:
    """Return the subdir mirror list configured for an agent."""
    return settings.drive_mirror_subdirs.get(agent_name, [])


def _guess_mime_type(name: str) -> str:
    """Best-effort MIME type guess for a filename.

    Falls back to ``application/octet-stream`` so unknown extensions still
    upload cleanly.

    Args:
        name: File basename or path.

    Returns:
        A MIME type string.
    """
    guessed, _ = mimetypes.guess_type(name)
    return guessed or "application/octet-stream"


# ---------------------------------------------------------------------------
# Mirror mapping state — separate ``thread_mirror_mappings`` table
# ---------------------------------------------------------------------------
#
# One row per linked thread; absence of a row means the thread isn't
# mirrored. The helpers below isolate the storage shape from the
# orchestration above.


async def _get_thread(thread_id: str) -> Thread | None:
    """Fetch the ``Thread`` row for a thread id.

    Args:
        thread_id: Thread id.

    Returns:
        The Thread ORM row, or ``None`` if the thread doesn't exist.
    """
    db = get_db()
    async with db() as session:
        return await session.get(Thread, thread_id)


async def _get_mapping(thread_id: str) -> ThreadMirrorMapping | None:
    """Fetch the mirror mapping row for a thread, if one exists.

    Args:
        thread_id: Thread id.

    Returns:
        The ``ThreadMirrorMapping`` ORM row, or ``None`` if the thread
        isn't currently linked to any mirror folder.
    """
    db = get_db()
    async with db() as session:
        return await session.get(ThreadMirrorMapping, thread_id)


async def _set_mapping(
    thread_id: str,
    provider: str,
    folder_id: str,
    thread_title: str | None = None,
) -> None:
    """Upsert the mirror mapping for a thread.

    Creates a row if none exists, otherwise updates the
    ``provider`` / ``folder_id`` / ``thread_title`` fields. The
    ``last_synced_at`` field is left untouched here — it's owned by
    ``_set_last_synced``.

    Args:
        thread_id: Thread id.
        provider: Provider key (``"google_drive"`` etc.).
        folder_id: Provider-side folder id.
        thread_title: Optional cached folder name for display.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(ThreadMirrorMapping, thread_id)
        if row is None:
            row = ThreadMirrorMapping(
                thread_id=thread_id,
                provider=provider,
                folder_id=folder_id,
                thread_title=thread_title,
            )
            session.add(row)
        else:
            row.provider = provider
            row.folder_id = folder_id
            if thread_title is not None:
                row.thread_title = thread_title
        await session.commit()


async def _delete_mapping(thread_id: str) -> bool:
    """Remove the mirror mapping for a thread, if any.

    Used by the unlink endpoint and by the link endpoint when re-linking
    a broken folder. Does NOT touch the provider — the Drive folder is
    intentionally orphaned (user can clean up manually if they want).

    Args:
        thread_id: Thread id.

    Returns:
        ``True`` if a mapping row was removed, ``False`` if there was
        nothing to remove.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(ThreadMirrorMapping, thread_id)
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
        return True


async def _set_last_synced(thread_id: str, when: datetime) -> None:
    """Update ``last_synced_at`` on the mirror mapping row.

    No-op if the thread has no mapping (i.e. the link was deleted in
    between sync start and end — race we tolerate silently).

    Args:
        thread_id: Thread id.
        when: Timestamp to record.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(ThreadMirrorMapping, thread_id)
        if row is None:
            return
        row.last_synced_at = when
        await session.commit()


# ---------------------------------------------------------------------------
# Provider abstract base
# ---------------------------------------------------------------------------


class MirrorProvider(ABC):
    """Abstract base for any mirror backend (Google Drive, SharePoint, …).

    Subclasses implement a small set of provider primitives. The base
    class composes them into the public sync API the run handler calls.

    Args:
        creds: The ``MirrorCredentials`` row for this (enterprise, provider).
            Held for the duration of an operation; the access token is
            minted lazily by the underlying SDK.
    """

    #: Stable identifier for the provider — must match the ``provider`` value
    #: stored in ``MirrorCredentials`` rows for this backend.
    provider_name: str = ""

    def __init__(self, creds: MirrorCredentials) -> None:
        self._creds = creds

    # -- Abstract provider primitives --------------------------------------

    @abstractmethod
    def find_or_create_folder(self, parent_id: str, name: str) -> str:
        """Find an existing child folder by name, or create one if missing.

        Args:
            parent_id: Provider-side id of the parent folder.
            name: Display name to look for / create.

        Returns:
            Provider-side id of the existing or newly-created folder.
        """

    @abstractmethod
    def create_folder(self, parent_id: str, name: str) -> str:
        """Unconditionally create a new folder named ``name`` under ``parent_id``.

        Used for per-thread folders where we want a fresh entry even if a
        same-named one happened to exist.

        Args:
            parent_id: Provider-side id of the parent folder.
            name: New folder's display name.

        Returns:
            Provider-side id of the new folder.
        """

    @abstractmethod
    def list_files_recursive(self, folder_id: str) -> list[dict[str, Any]]:
        """Walk a folder tree and return a flat list of files.

        Each entry must contain at least: ``id``, ``name``, ``mimeType``,
        ``modifiedTime`` (provider's ISO 8601 string), ``relative_path``
        (the file's path relative to ``folder_id``, joined by ``/``).

        Args:
            folder_id: Provider-side id of the root folder to walk.

        Returns:
            Flat list of file metadata dicts.
        """

    @abstractmethod
    def download_file(self, file_id: str) -> bytes:
        """Download the binary contents of a file.

        Args:
            file_id: Provider-side id of the file.

        Returns:
            File bytes.
        """

    @abstractmethod
    def upload_new_file(
        self, parent_id: str, name: str, content: bytes, mime_type: str
    ) -> str:
        """Create a new file under ``parent_id`` with the given content.

        Args:
            parent_id: Provider-side id of the parent folder.
            name: File basename.
            content: Bytes to upload.
            mime_type: MIME type for the upload.

        Returns:
            Provider-side id of the new file.
        """

    @abstractmethod
    def update_file_content(
        self, file_id: str, content: bytes, mime_type: str
    ) -> None:
        """Replace the contents of an existing file (preserves ``file_id``).

        Args:
            file_id: Provider-side id of the file to overwrite.
            content: New bytes.
            mime_type: MIME type for the upload.
        """

    @abstractmethod
    def get_folder_metadata(self, folder_id: str) -> dict[str, Any] | None:
        """Return folder metadata by id, or ``None`` if missing/inaccessible.

        Used to detect a broken link — when our mapping points at a
        folder that has been deleted or trashed on the provider side.
        Implementations should treat 404 and ``trashed=True`` (or the
        provider equivalent) as ``None``.

        Args:
            folder_id: Provider-side folder id.

        Returns:
            A dict with at least ``id`` and ``name`` if reachable;
            otherwise ``None``.
        """

    @abstractmethod
    def is_native_format(self, mime_type: str) -> bool:
        """Whether a MIME type is a provider-native, non-binary format we skip.

        Google Docs (``application/vnd.google-apps.*``) round-trip badly to
        bytes and are excluded from sync. Most providers (notably SharePoint)
        always return ``False`` since their docs are real ``.docx`` blobs.

        Args:
            mime_type: MIME type string from a file metadata dict.

        Returns:
            ``True`` if the file should be skipped during sync.
        """

    @abstractmethod
    def parse_modified_time(self, value: str | None) -> datetime | None:
        """Parse the provider's ISO 8601 timestamp string to naive UTC.

        Args:
            value: Timestamp string from a file metadata dict.

        Returns:
            Naive UTC ``datetime`` or ``None`` if ``value`` was falsy.
        """

    # -- Concrete shared orchestration -------------------------------------

    async def setup_thread_folder(
        self,
        enterprise_id: str,
        thread_id: str,
        agent_name: str,
        folder_name: str | None = None,
    ) -> Thread | None:
        """Provision the per-thread mirror folder structure if missing.

        Creates::

            <parent>/{agent_name}/{folder_name}/
                input/
                output/
                ...mirrored subdirs from settings.drive_mirror_subdirs...

        Idempotent — subsequent calls return the existing thread row
        without touching the provider.

        Args:
            enterprise_id: Tenant id (unused for now; reserved for future
                multi-provider routing).
            thread_id: Thread id. The thread row must already exist.
            agent_name: Graph name (becomes a subfolder under the parent).
            folder_name: Display name for the per-thread folder. ``None``
                falls back to a generated codename
                (``"saffron-meadow-274"`` style) — used by callers that
                don't have a user-supplied name. The mirror REST API
                always supplies one.

        Returns:
            The ``Thread`` row if the linkage is in place (existing or
            newly created), or ``None`` if no parent folder has been
            registered yet or the thread row is missing.
        """
        if not self._creds.parent_folder_id:
            return None

        thread = await _get_thread(thread_id)
        if thread is None:
            # Caller is expected to have created the thread row before
            # invoking us; if it's missing we silently skip rather than
            # create one here.
            logger.warning("setup_thread_folder: no thread row for %s", thread_id)
            return None

        existing = await _get_mapping(thread_id)
        if existing is not None:
            return thread

        title = folder_name or generate_thread_title()
        parent_id = self._creds.parent_folder_id
        mirror_subdirs = _mirror_subdirs_for(agent_name)

        def _build() -> str:
            agent_folder_id = self.find_or_create_folder(parent_id, agent_name)
            thread_folder_id = self.create_folder(agent_folder_id, title)
            for subdir in mirror_subdirs:
                self.find_or_create_folder(thread_folder_id, subdir)
            return thread_folder_id

        provider_folder_id = await asyncio.to_thread(_build)

        await _set_mapping(
            thread_id=thread_id,
            provider=self.provider_name,
            folder_id=provider_folder_id,
            thread_title=title,
        )
        logger.info(
            "Provisioned %s folder %s for thread %s (title=%r) under %s/%s",
            self.provider_name,
            provider_folder_id,
            thread_id,
            title,
            agent_name,
            title,
        )
        return thread

    async def sync_in(
        self, enterprise_id: str, thread_id: str, agent_name: str
    ) -> int:
        """Pull user-edited files from the provider into S3.

        For each mirrored subdir, walks the provider folder and downloads
        any file whose ``modifiedTime`` is newer than
        ``mirror_last_synced_at`` (or every file on the very first sync).
        Native non-binary formats are skipped (see :meth:`is_native_format`).

        Args:
            enterprise_id: Tenant id.
            thread_id: Thread id.
            agent_name: Graph name (decides mirror policy).

        Returns:
            Number of files pulled. ``0`` if the thread has no mirror folder.
        """
        mapping = await _get_mapping(thread_id)
        if mapping is None:
            return 0

        mirror_subdirs = _mirror_subdirs_for(agent_name)
        if not mirror_subdirs:
            return 0

        cutoff = mapping.last_synced_at  # may be None
        folder_id = mapping.folder_id
        provider = self  # capture for the worker

        def _do_sync() -> int:
            pulled = 0
            for subdir in mirror_subdirs:
                subdir_id = provider.find_or_create_folder(folder_id, subdir)
                files = provider.list_files_recursive(subdir_id)
                for f in files:
                    if provider.is_native_format(f["mimeType"]):
                        logger.info(
                            "Skipping native format %s (%s)",
                            f["relative_path"], f["mimeType"],
                        )
                        continue
                    modified = provider.parse_modified_time(f.get("modifiedTime"))
                    if cutoff is not None and modified is not None and modified <= cutoff:
                        continue
                    content = provider.download_file(f["id"])
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
        self, enterprise_id: str, thread_id: str, agent_name: str
    ) -> int:
        """Push agent-written files from S3 to the provider.

        Walks each mirrored S3 subdir and uploads files whose mtime is
        newer than ``mirror_last_synced_at`` (or every file on the first
        sync). For each S3 file we look up the matching provider file by
        relative path; if one exists we update its content (preserving the
        provider id), otherwise we create a new file. Subfolders are
        created on demand. Updates ``mirror_last_synced_at`` after success.

        Args:
            enterprise_id: Tenant id.
            thread_id: Thread id.
            agent_name: Graph name.

        Returns:
            Number of files pushed. ``0`` if the thread has no mirror folder.
        """
        mapping = await _get_mapping(thread_id)
        if mapping is None:
            return 0

        mirror_subdirs = _mirror_subdirs_for(agent_name)
        if not mirror_subdirs:
            return 0

        cutoff = mapping.last_synced_at  # may be None
        folder_id = mapping.folder_id
        provider = self

        def _do_sync() -> int:
            pushed = 0
            for subdir in mirror_subdirs:
                local_root = _s3_subdir_root(enterprise_id, thread_id, subdir)
                if not local_root.exists():
                    continue
                subdir_id = provider.find_or_create_folder(folder_id, subdir)
                # Index existing provider contents once for id lookup.
                existing = provider.list_files_recursive(subdir_id)
                by_path: dict[str, dict[str, Any]] = {
                    f["relative_path"]: f for f in existing
                }

                for src in sorted(local_root.rglob("*")):
                    if not src.is_file():
                        continue
                    # Skip ``.keep`` placeholders dropped by the file
                    # manager scaffolder — they exist only to make empty
                    # folders discoverable in S3 and have no value on Drive.
                    if src.name == ".keep":
                        continue
                    rel = src.relative_to(local_root).as_posix()
                    if cutoff is not None:
                        mtime = datetime.utcfromtimestamp(src.stat().st_mtime)
                        if mtime <= cutoff:
                            continue
                    content = src.read_bytes()
                    mime = _guess_mime_type(src.name)

                    match = by_path.get(rel)
                    if match:
                        provider.update_file_content(match["id"], content, mime)
                    else:
                        # Walk/create intermediate folders, then upload.
                        parent_id = subdir_id
                        parts = rel.split("/")
                        for part in parts[:-1]:
                            parent_id = provider.find_or_create_folder(
                                parent_id, part
                            )
                        provider.upload_new_file(
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
        # Capture timestamp *after* uploads complete so a subsequent sync_in
        # does not re-pull the files we just pushed.
        await _set_last_synced(thread_id, datetime.utcnow())
        return pushed

    # -- Provider-level helpers used by the OAuth router --------------------

    async def verify_folder_access(self, folder_id: str) -> None:
        """Confirm the agent identity can read a given folder.

        Used at folder-registration time to surface "you forgot to share
        the folder" errors before persisting. Raises whatever the provider
        SDK raises on access failure.

        Args:
            folder_id: Provider-side folder id to test.
        """
        await asyncio.to_thread(self.list_files_recursive, folder_id)
