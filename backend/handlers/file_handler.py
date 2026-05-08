"""Thread-scoped file manager orchestration.

Five operations on the per-thread virtual filesystem rooted at the
agent's workspace prefix (``enterprise/{eid}/workspaces/{tid}/``) — the
*same* keys the agent's ``S3Backend`` reads/writes and the Drive mirror
syncs. So a paperclip upload here is immediately visible to the agent
and pushed to the user's Drive folder on the next ``sync_out``.

Operations:

* ``list_files`` — list under a relative prefix.
* ``read_file`` — read one file's contents (UTF-8 text).
* ``write_file`` — write/replace one file from a JSON body.
* ``upload_files`` — multipart batch upload into a folder, preserving filenames.
* ``delete_file`` — delete one file.
* ``scaffold_folders`` — drop ``.keep`` placeholder files so newly
  created threads have a discoverable folder layout.

All paths returned to the caller are *thread-relative* — the
``enterprise/{eid}/workspaces/{tid}/`` storage prefix is added on the
way down to the storage adapter and stripped on the way back up.
Permission checks go through ``FilePolicy`` (actor=``"user"`` for
everything reachable from the REST surface; the agent's tools will
call the same handlers with ``actor="agent"``).
"""

from fastapi import HTTPException, UploadFile

from backend.infra.registry import get_storage
from backend.schemas.files import FileContent, FileObject, WriteResult
from backend.services.agent.workspace import workspace_prefix
from backend.services.file_policy import FilePolicy, READ, WRITE

# Names hidden from list responses — internal placeholders for empty
# folders. Drive mirror's ``sync_out`` also skips these by name.
_HIDDEN_NAMES = frozenset({".keep"})

# Folders scaffolded on thread creation. ``.keep`` markers go in each so
# the layout is discoverable via ``list_files`` immediately, before any
# real content lands.
_SCAFFOLD_FOLDERS = ("input/userUpload", "output")


def _validate_id(thread_id: str, enterprise_id: str) -> None:
    """Reject malformed ids before they reach the storage layer."""
    for label, value in (("thread_id", thread_id), ("enterprise_id", enterprise_id)):
        if not value or "/" in value or ".." in value:
            raise HTTPException(status_code=400, detail=f"Invalid {label}: {value!r}")


def _to_storage_key(enterprise_id: str, thread_id: str, rel_path: str) -> str:
    """Turn a thread-relative path into a full storage key."""
    _validate_id(thread_id, enterprise_id)
    return f"{workspace_prefix(enterprise_id, thread_id)}/{rel_path.lstrip('/')}"


def _from_storage_key(enterprise_id: str, thread_id: str, storage_key: str) -> str:
    """Strip the workspace prefix from a storage key for client display."""
    root = workspace_prefix(enterprise_id, thread_id) + "/"
    return storage_key[len(root) :] if storage_key.startswith(root) else storage_key


async def list_files(
    enterprise_id: str,
    thread_id: str,
    prefix: str = "",
    actor: str = "user",
) -> list[FileObject]:
    """List every file beneath ``prefix`` (thread-relative).

    The empty prefix lists every file in the thread, filtered down to
    items the actor has read access to. ``.keep`` placeholder files
    are hidden from the response.

    Args:
        enterprise_id: Caller's tenant id.
        thread_id: The thread's id (URL segment).
        prefix: Thread-relative folder prefix. Empty means thread root.
        actor: ``"user"`` or ``"agent"``.

    Returns:
        Files matching ``prefix`` that the actor has read access to.
    """
    _validate_id(thread_id, enterprise_id)
    storage = get_storage()
    storage_prefix = workspace_prefix(enterprise_id, thread_id)
    if prefix:
        # Permission check on the folder being listed; only enforced when
        # the caller targets a specific folder. The empty-prefix case
        # falls through to per-item filtering below.
        FilePolicy.check(prefix, actor, READ)
        storage_prefix = f"{storage_prefix}/{prefix.lstrip('/').rstrip('/')}/"

    raw = storage.list_objects(storage_prefix)
    out: list[FileObject] = []
    for obj in raw:
        rel = _from_storage_key(enterprise_id, thread_id, obj["key"])
        if rel.rsplit("/", 1)[-1] in _HIDDEN_NAMES:
            continue
        # Filter out items the actor can't read — covers the empty-prefix
        # case where we listed the entire thread.
        if not FilePolicy.can(rel, actor, READ):
            continue
        out.append(
            FileObject(
                key=rel,
                size=obj["size"],
                modified_at=obj["modified_at"],
            )
        )
    return out


async def read_file(
    enterprise_id: str, thread_id: str, path: str, actor: str = "user"
) -> FileContent:
    """Read one file's contents as UTF-8 text.

    Args:
        enterprise_id: Caller's tenant id.
        thread_id: The thread's id.
        path: Thread-relative path of the file to read.
        actor: ``"user"`` or ``"agent"``.

    Returns:
        ``FileContent`` with the relative key, body, and size.

    Raises:
        HTTPException: 400 on invalid path; 403 on policy denial; 404
            if the object doesn't exist.
    """
    FilePolicy.check(path, actor, READ)
    storage = get_storage()
    key = _to_storage_key(enterprise_id, thread_id, path)
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    content = storage.read_text(key)
    return FileContent(
        key=path,
        content=content,
        size=len(content.encode("utf-8")),
    )


async def write_file(
    enterprise_id: str,
    thread_id: str,
    path: str,
    content: str,
    actor: str = "user",
) -> WriteResult:
    """Write or replace one file from a text body.

    Args:
        enterprise_id: Caller's tenant id.
        thread_id: The thread's id.
        path: Thread-relative destination path.
        content: UTF-8 text to write. Existing object is overwritten.
        actor: ``"user"`` or ``"agent"``.

    Returns:
        ``WriteResult`` with the relative key and final size.

    Raises:
        HTTPException: 400 on invalid path; 403 on policy denial.
    """
    FilePolicy.check(path, actor, WRITE)
    storage = get_storage()
    key = _to_storage_key(enterprise_id, thread_id, path)
    storage.write_text(key, content)
    return WriteResult(key=path, size=len(content.encode("utf-8")))


async def upload_files(
    enterprise_id: str,
    thread_id: str,
    folder: str,
    files: list[UploadFile],
    actor: str = "user",
) -> list[WriteResult]:
    """Persist multipart uploads into ``folder`` (thread-relative).

    Each part's filename is preserved; collisions overwrite. Use this
    instead of PUT for binary content (PDF, DOCX, images).

    Args:
        enterprise_id: Caller's tenant id.
        thread_id: The thread's id.
        folder: Thread-relative destination folder.
        files: Multipart parts received by the router.
        actor: ``"user"`` or ``"agent"``.

    Returns:
        One ``WriteResult`` per saved file, in input order.

    Raises:
        HTTPException: 400 on invalid folder/filename; 403 on policy denial.
    """
    folder = folder.strip("/")
    out: list[WriteResult] = []
    for f in files:
        filename = (f.filename or "").strip("/")
        if not filename or "/" in filename or ".." in filename:
            raise HTTPException(
                status_code=400, detail=f"Invalid filename: {filename!r}"
            )
        rel = f"{folder}/{filename}" if folder else filename
        FilePolicy.check(rel, actor, WRITE)
        storage = get_storage()
        # ``UploadFile.read`` returns the full body — fine for chat-sized
        # attachments. Switch to streaming for large files later.
        body = await f.read()
        storage.write(_to_storage_key(enterprise_id, thread_id, rel), body)
        out.append(WriteResult(key=rel, size=len(body)))
    return out


async def delete_file(
    enterprise_id: str, thread_id: str, path: str, actor: str = "user"
) -> None:
    """Delete one file.

    Args:
        enterprise_id: Caller's tenant id.
        thread_id: The thread's id.
        path: Thread-relative path of the file to delete.
        actor: ``"user"`` or ``"agent"``.

    Raises:
        HTTPException: 400 on invalid path; 403 on policy denial; 404
            if the object doesn't exist.
    """
    FilePolicy.check(path, actor, WRITE)
    storage = get_storage()
    key = _to_storage_key(enterprise_id, thread_id, path)
    if not storage.exists(key):
        raise HTTPException(status_code=404, detail=f"File not found: {path}")
    # ``LocalStorage`` doesn't yet expose a ``delete`` method — reach
    # through ``abs_path`` for now. When ``BotoS3Storage`` lands, add a
    # proper delete method to the adapter and switch this caller.
    from pathlib import Path

    Path(storage.abs_path(key)).unlink()


async def scaffold_folders(enterprise_id: str, thread_id: str) -> None:
    """Create the standard folder layout for a freshly created thread.

    Drops a ``.keep`` placeholder under each scaffold folder so the
    layout is discoverable via ``list_files`` before any real content
    lands. ``.keep`` files are hidden from list responses and excluded
    from the Drive mirror's ``sync_out``.

    Args:
        enterprise_id: Caller's tenant id.
        thread_id: The thread's id.
    """
    _validate_id(thread_id, enterprise_id)
    storage = get_storage()
    for folder in _SCAFFOLD_FOLDERS:
        key = _to_storage_key(enterprise_id, thread_id, f"{folder}/.keep")
        if not storage.exists(key):
            storage.write(key, b"")
