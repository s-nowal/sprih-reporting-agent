"""S3-style ``BackendProtocol`` implementation for deepagents.

Implements the deepagents file-tool surface (``read``, ``write``, ``edit``,
``ls_info``, ``glob_info``, ``grep_raw``, ``upload_files``,
``download_files``) using only S3-style storage operations: ``read``,
``write``, ``exists``, ``list_objects``.

Because the backend never assumes a local filesystem, the same code path
works against the in-repo mock (``LocalStorage``) and a future
``BotoS3Storage`` that talks to real AWS S3. Swapping storages is a
configuration change with zero edits inside this module.

Files in the agent's view live at virtual paths like ``/input/foo.txt``.
The backend prefixes those onto a thread-scoped storage root (e.g.
``enterprise/{eid}/workspaces/{tid}``) to form the actual storage key
``enterprise/{eid}/workspaces/{tid}/input/foo.txt``.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import wcmatch.glob as wcglob
from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    FileDownloadResponse,
    FileInfo,
    FileUploadResponse,
    GrepMatch,
    WriteResult,
)
from deepagents.backends.utils import (
    check_empty_content,
    format_content_with_line_numbers,
    perform_string_replacement,
)

# Skip files larger than this when running ``grep_raw``. Mirrors the
# default in ``FilesystemBackend`` so the LLM sees comparable behaviour.
_MAX_GREP_FILE_SIZE_BYTES = 10 * 1024 * 1024


class S3Backend(BackendProtocol):
    """Deepagents backend that talks to an S3-style object store.

    Args:
        storage: Object adapter exposing ``read(key)``, ``write(key, bytes)``,
            ``exists(key)``, and ``list_objects(prefix)``. ``LocalStorage``
            satisfies this today; a future ``BotoS3Storage`` will too.
        prefix: Storage-relative key prefix that scopes every operation
            (e.g. ``"enterprise/eid/workspaces/tid"``). Leading and
            trailing slashes are stripped.
    """

    def __init__(self, storage: Any, prefix: str) -> None:
        self._storage = storage
        self._prefix = prefix.strip("/")

    # ---------------------------------------------------------------------
    # Path helpers
    # ---------------------------------------------------------------------

    def _normalize(self, virtual_path: str) -> str:
        """Validate a virtual path and return it as ``"/foo/bar"`` form.

        Args:
            virtual_path: Caller-provided path (absolute or relative).

        Returns:
            Path starting with ``/`` and free of traversal components.

        Raises:
            ValueError: On ``..`` / ``~`` traversal attempts.
        """
        path = virtual_path if virtual_path.startswith("/") else "/" + virtual_path
        parts = PurePosixPath(path).parts
        if ".." in parts or path.startswith("/~") or "~" in parts:
            raise ValueError(f"Path traversal not allowed: {virtual_path}")
        return path

    def _key(self, virtual_path: str) -> str:
        """Translate a virtual path to a fully-qualified storage key.

        Args:
            virtual_path: Caller-provided virtual path.

        Returns:
            ``"<prefix><normalized>"`` (e.g.
            ``"enterprise/eid/workspaces/tid/input/foo.txt"``).
        """
        normalized = self._normalize(virtual_path)
        # Strip leading "/" to compose without producing "//".
        return f"{self._prefix}{normalized}" if self._prefix else normalized.lstrip("/")

    def _to_virtual(self, key: str) -> str:
        """Translate a storage key back to a virtual path.

        Args:
            key: Storage key produced by ``list_objects``.

        Returns:
            Virtual path beginning with ``/``. If ``key`` falls outside the
            backend's prefix, the original key is returned unchanged
            (which only happens if storage returns garbage).
        """
        if self._prefix and key.startswith(self._prefix + "/"):
            return "/" + key[len(self._prefix) + 1 :]
        if not self._prefix:
            return "/" + key
        return key

    def _list_under(self, virtual_dir: str) -> list[dict]:
        """List storage objects whose key sits under ``virtual_dir``.

        Args:
            virtual_dir: Virtual directory path (``"/"`` for the root).

        Returns:
            Raw object records from the storage adapter (each with
            ``key``, ``size``, ``modified_at``).
        """
        normalized = self._normalize(virtual_dir)
        # Build a key prefix ending in "/" to avoid accidentally matching
        # sibling keys that happen to share a name prefix.
        rel = normalized.lstrip("/")
        if rel and not rel.endswith("/"):
            rel += "/"
        list_prefix = f"{self._prefix}/{rel}" if self._prefix else rel
        return self._storage.list_objects(list_prefix)

    # ---------------------------------------------------------------------
    # BackendProtocol — single-file ops
    # ---------------------------------------------------------------------

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> str:
        """Read a file and return its content with line numbers.

        Args:
            file_path: Virtual path of the file.
            offset: 0-indexed start line.
            limit: Maximum number of lines to return.

        Returns:
            ``cat -n`` style content, an "empty file" marker, or an
            error string. Never raises.
        """
        try:
            key = self._key(file_path)
        except ValueError as e:
            return f"Error: {e}"
        if not self._storage.exists(key):
            return f"Error: File '{file_path}' not found"
        try:
            content = self._storage.read(key).decode("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return f"Error reading file '{file_path}': {e}"

        empty = check_empty_content(content)
        if empty:
            return empty

        lines = content.splitlines()
        if offset >= len(lines):
            return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"
        end = min(offset + limit, len(lines))
        return format_content_with_line_numbers(lines[offset:end], start_line=offset + 1)

    def write(self, file_path: str, content: str) -> WriteResult:
        """Create a new file. Errors if the key already exists.

        Args:
            file_path: Virtual path of the file.
            content: UTF-8 text to store.

        Returns:
            ``WriteResult`` with ``path`` set on success (and
            ``files_update=None`` since we persist externally), or
            ``error`` set on failure.
        """
        try:
            key = self._key(file_path)
        except ValueError as e:
            return WriteResult(error=str(e))
        if self._storage.exists(key):
            return WriteResult(
                error=(
                    f"Cannot write to {file_path} because it already exists. "
                    "Read and then make an edit, or write to a new path."
                )
            )
        try:
            self._storage.write(key, content.encode("utf-8"))
        except (OSError, UnicodeEncodeError) as e:
            return WriteResult(error=f"Error writing file '{file_path}': {e}")
        return WriteResult(path=file_path, files_update=None)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        """Replace ``old_string`` with ``new_string`` in an existing file.

        Args:
            file_path: Virtual path of the file.
            old_string: Exact substring to find.
            new_string: Replacement text.
            replace_all: If ``False``, ``old_string`` must be unique.

        Returns:
            ``EditResult`` with ``occurrences`` on success or ``error`` set
            on failure (including "file not found" and "string not found").
        """
        try:
            key = self._key(file_path)
        except ValueError as e:
            return EditResult(error=str(e))
        if not self._storage.exists(key):
            return EditResult(error=f"Error: File '{file_path}' not found")
        try:
            content = self._storage.read(key).decode("utf-8")
        except (OSError, UnicodeDecodeError) as e:
            return EditResult(error=f"Error reading file '{file_path}': {e}")

        result = perform_string_replacement(content, old_string, new_string, replace_all)
        if isinstance(result, str):
            return EditResult(error=result)
        new_content, occurrences = result

        try:
            self._storage.write(key, new_content.encode("utf-8"))
        except (OSError, UnicodeEncodeError) as e:
            return EditResult(error=f"Error writing file '{file_path}': {e}")
        return EditResult(path=file_path, files_update=None, occurrences=int(occurrences))

    # ---------------------------------------------------------------------
    # BackendProtocol — listing / search
    # ---------------------------------------------------------------------

    def ls_info(self, path: str) -> list[FileInfo]:
        """List immediate children (one level deep) of a virtual directory.

        S3 has no real directories, so subdirectory entries are synthesised
        from the keys themselves: any key with a path component beneath
        ``path`` produces a directory entry for that component.

        Args:
            path: Virtual directory path.

        Returns:
            ``FileInfo`` entries for direct file children plus ``is_dir=True``
            entries for synthetic subdirectories. Empty if nothing matches.
        """
        try:
            normalized = self._normalize(path)
        except ValueError:
            return []
        # Build virtual prefix used to compute relative paths.
        virt_dir = normalized.rstrip("/") if normalized != "/" else ""

        objects = self._list_under(normalized)
        files: list[FileInfo] = []
        subdirs: dict[str, str] = {}  # name -> latest modified_at
        for obj in objects:
            virt = self._to_virtual(obj["key"])
            if virt_dir:
                if not virt.startswith(virt_dir + "/"):
                    continue
                rel = virt[len(virt_dir) + 1 :]
            else:
                rel = virt.lstrip("/")
            if "/" in rel:
                head = rel.split("/", 1)[0]
                prev = subdirs.get(head)
                if prev is None or obj["modified_at"] > prev:
                    subdirs[head] = obj["modified_at"]
                continue
            files.append({
                "path": virt,
                "is_dir": False,
                "size": int(obj["size"]),
                "modified_at": obj["modified_at"],
            })

        for name, modified_at in subdirs.items():
            child_path = f"{virt_dir}/{name}/" if virt_dir else f"/{name}/"
            files.append({
                "path": child_path,
                "is_dir": True,
                "size": 0,
                "modified_at": modified_at,
            })

        files.sort(key=lambda x: x.get("path", ""))
        return files

    def glob_info(self, pattern: str, path: str = "/") -> list[FileInfo]:
        """Find files whose path (relative to ``path``) matches ``pattern``.

        Args:
            pattern: Glob pattern (``*``, ``**``, ``?``, ``[abc]``).
            path: Base virtual directory.

        Returns:
            Sorted list of ``FileInfo`` entries.

        Raises:
            ValueError: If ``pattern`` contains ``..``.
        """
        if pattern.startswith("/"):
            pattern = pattern.lstrip("/")
        if ".." in Path(pattern).parts:
            raise ValueError("Path traversal not allowed in glob pattern")

        try:
            normalized = self._normalize(path)
        except ValueError:
            return []
        virt_dir = normalized.rstrip("/") if normalized != "/" else ""

        objects = self._list_under(normalized)
        results: list[FileInfo] = []
        for obj in objects:
            virt = self._to_virtual(obj["key"])
            rel = virt[len(virt_dir) + 1 :] if virt_dir else virt.lstrip("/")
            if not wcglob.globmatch(rel, pattern, flags=wcglob.BRACE | wcglob.GLOBSTAR):
                continue
            results.append({
                "path": virt,
                "is_dir": False,
                "size": int(obj["size"]),
                "modified_at": obj["modified_at"],
            })
        results.sort(key=lambda x: x.get("path", ""))
        return results

    def grep_raw(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
    ) -> list[GrepMatch] | str:
        """Scan files under ``path`` for a literal substring ``pattern``.

        Files larger than 10 MiB are skipped, matching ``FilesystemBackend``.
        Unlike that backend we never shell out to ripgrep — the backend
        must work the same way against real S3.

        Args:
            pattern: Literal substring to find (not a regex).
            path: Virtual directory to scan. Defaults to ``"/"``.
            glob: Optional glob filter applied to file paths relative to
                ``path``.

        Returns:
            List of ``GrepMatch`` entries.
        """
        try:
            normalized = self._normalize(path or "/")
        except ValueError:
            return []
        virt_dir = normalized.rstrip("/") if normalized != "/" else ""

        objects = self._list_under(normalized)
        matches: list[GrepMatch] = []
        for obj in objects:
            if obj["size"] > _MAX_GREP_FILE_SIZE_BYTES:
                continue
            virt = self._to_virtual(obj["key"])
            rel = virt[len(virt_dir) + 1 :] if virt_dir else virt.lstrip("/")
            if glob and not wcglob.globmatch(
                rel, glob, flags=wcglob.BRACE | wcglob.GLOBSTAR
            ):
                continue
            try:
                content = self._storage.read(obj["key"]).decode("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for line_num, line in enumerate(content.splitlines(), 1):
                if pattern in line:
                    matches.append({"path": virt, "line": line_num, "text": line})
        return matches

    # ---------------------------------------------------------------------
    # BackendProtocol — bulk binary I/O
    # ---------------------------------------------------------------------

    def upload_files(
        self, files: list[tuple[str, bytes]]
    ) -> list[FileUploadResponse]:
        """Write multiple binary files. Per-file success/failure reporting.

        Args:
            files: ``(virtual_path, content)`` tuples to write.

        Returns:
            One ``FileUploadResponse`` per input file in matching order.
        """
        responses: list[FileUploadResponse] = []
        for path, content in files:
            try:
                key = self._key(path)
            except ValueError:
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            try:
                self._storage.write(key, content)
            except OSError:
                responses.append(FileUploadResponse(path=path, error="invalid_path"))
                continue
            responses.append(FileUploadResponse(path=path, error=None))
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """Read multiple binary files. Per-file success/failure reporting.

        Args:
            paths: Virtual paths to read.

        Returns:
            One ``FileDownloadResponse`` per input path in matching order.
        """
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                key = self._key(path)
            except ValueError:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            if not self._storage.exists(key):
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="file_not_found")
                )
                continue
            try:
                content = self._storage.read(key)
            except OSError:
                responses.append(
                    FileDownloadResponse(path=path, content=None, error="invalid_path")
                )
                continue
            responses.append(
                FileDownloadResponse(path=path, content=content, error=None)
            )
        return responses
