"""In-memory stub ``MirrorProvider`` for e2e tests.

Implements the subset of ``MirrorProvider`` primitives needed to exercise
the link / status / sync workflows without touching a real Drive backend.
Folder ids, file ids, and contents live in module-level dicts so tests
can inspect them. Call :func:`reset_state` at the start of every test
that uses the stub to avoid cross-test bleed.

The provider registers under ``provider_name="stub"``. Tests opt in by
inserting a ``mirror_credentials`` row with ``provider="stub"`` (see the
``stub_mirror_credentials`` fixture in ``conftest.py``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from backend.services.mirror.base import MirrorProvider

# Module-level in-memory state. Reset by reset_state().
_FOLDERS: dict[str, dict[str, Any]] = {}
"""folder_id → {"name": str, "parent_id": str | None}"""

_FILES: dict[str, dict[str, Any]] = {}
"""file_id → {"name": str, "parent_id": str, "content": bytes, "mime_type": str}"""


def reset_state() -> None:
    """Clear all in-memory folders and files. Call at the start of each test."""
    _FOLDERS.clear()
    _FILES.clear()


def register_root_folder(folder_id: str, name: str = "test-root") -> str:
    """Seed a root folder so tests can use its id as the ``parent_folder_id``.

    Args:
        folder_id: Id to register the root under.
        name: Display name for the root.

    Returns:
        The folder_id (echoed for chaining convenience).
    """
    _FOLDERS[folder_id] = {"name": name, "parent_id": None}
    return folder_id


def snapshot_folders() -> dict[str, dict[str, Any]]:
    """Return a copy of the folder map for test inspection."""
    return {k: dict(v) for k, v in _FOLDERS.items()}


def snapshot_files() -> dict[str, dict[str, Any]]:
    """Return a copy of the file map for test inspection."""
    return {k: dict(v) for k, v in _FILES.items()}


class StubMirrorProvider(MirrorProvider):
    """In-memory ``MirrorProvider`` used by tests. No network calls."""

    provider_name = "stub"

    # -- Folder primitives ----------------------------------------------------

    def find_or_create_folder(self, parent_id: str, name: str) -> str:
        """Return the id of a child folder named ``name`` under ``parent_id``.

        Creates one if none exists.
        """
        for fid, meta in _FOLDERS.items():
            if meta.get("parent_id") == parent_id and meta.get("name") == name:
                return fid
        return self.create_folder(parent_id, name)

    def create_folder(self, parent_id: str, name: str) -> str:
        """Unconditionally create a new folder under ``parent_id``."""
        folder_id = f"stub_folder_{uuid.uuid4().hex[:12]}"
        _FOLDERS[folder_id] = {"name": name, "parent_id": parent_id}
        return folder_id

    def get_folder_metadata(self, folder_id: str) -> dict[str, Any] | None:
        """Return ``{"id", "name"}`` if folder exists, else ``None``."""
        meta = _FOLDERS.get(folder_id)
        if meta is None:
            return None
        return {"id": folder_id, "name": meta["name"]}

    # -- File primitives ------------------------------------------------------

    def list_files_recursive(self, folder_id: str) -> list[dict[str, Any]]:
        """Walk the folder tree under ``folder_id`` and return all files."""
        scope = self._descendant_folder_ids(folder_id) | {folder_id}
        results: list[dict[str, Any]] = []
        for fid, meta in _FILES.items():
            if meta["parent_id"] not in scope:
                continue
            results.append({
                "id": fid,
                "name": meta["name"],
                "mimeType": meta["mime_type"],
                "modifiedTime": "2026-01-01T00:00:00Z",
                "relative_path": meta["name"],
            })
        return results

    def download_file(self, file_id: str) -> bytes:
        """Return the bytes of a previously-stored file."""
        return _FILES[file_id]["content"]

    def upload_new_file(
        self, parent_id: str, name: str, content: bytes, mime_type: str
    ) -> str:
        """Create a new file under ``parent_id`` and return its new id."""
        file_id = f"stub_file_{uuid.uuid4().hex[:12]}"
        _FILES[file_id] = {
            "name": name,
            "parent_id": parent_id,
            "content": content,
            "mime_type": mime_type,
        }
        return file_id

    def update_file_content(
        self, file_id: str, content: bytes, mime_type: str
    ) -> None:
        """Replace an existing file's content (preserves its id)."""
        if file_id not in _FILES:
            raise KeyError(f"stub: file {file_id!r} does not exist")
        _FILES[file_id]["content"] = content
        _FILES[file_id]["mime_type"] = mime_type

    # -- Format helpers -------------------------------------------------------

    def is_native_format(self, mime_type: str) -> bool:
        """The stub treats every blob as a real file (no native formats)."""
        return False

    def parse_modified_time(self, value: str | None) -> datetime | None:
        """Parse the stub's ISO 8601 timestamp into a naive UTC datetime."""
        if not value:
            return None
        return (
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            .replace(tzinfo=None)
        )

    # -- Helpers --------------------------------------------------------------

    def _descendant_folder_ids(self, folder_id: str) -> set[str]:
        """Return ids of every folder descending from ``folder_id`` (excl. self)."""
        result: set[str] = set()
        stack = [folder_id]
        while stack:
            current = stack.pop()
            for fid, meta in _FOLDERS.items():
                if meta.get("parent_id") == current and fid not in result:
                    result.add(fid)
                    stack.append(fid)
        return result
