"""Thread-scoped file manager.

Single endpoint at ``/threads/{thread_id}/files`` with the operation
chosen by HTTP verb + a query parameter:

* ``GET    ?prefix=...``     — list files under a folder (omit prefix → thread root).
* ``GET    ?path=...``       — read one file as UTF-8 text.
* ``PUT    ?path=...``       — write/replace one file from a JSON body.
* ``POST   ?folder=...``     — multipart batch upload (preserves filenames).
* ``DELETE ?path=...``       — delete one file.

Folder access is enforced by ``FilePolicy`` — see
``backend/services/file_policy.py``. The REST surface is the only place
``actor="user"`` is hard-wired; in-process agent tools will call the
same handlers with ``actor="agent"``.

Storage layout is the same prefix the agent's ``S3Backend`` and Drive
mirror use — ``enterprise/{eid}/workspaces/{tid}/`` — so files written
through this router are immediately visible to the agent and pushed to
the user's Drive folder on the next ``sync_out``.
"""

from fastapi import APIRouter, Depends, Query, UploadFile

from backend.handlers import file_handler
from backend.schemas.files import (
    FileContent,
    FileObject,
    WriteFileRequest,
    WriteResult,
)
from backend.security.auth import EnterpriseContext, get_enterprise_context

router = APIRouter(tags=["files"])


@router.get(
    "/threads/{thread_id}/files",
    # Either FileContent (read) or list[FileObject] (list); FastAPI's
    # ``response_model`` doesn't union neatly, so we omit it here and
    # rely on the handler's typed returns.
)
async def list_or_read(
    thread_id: str,
    prefix: str | None = Query(default=None),
    path: str | None = Query(default=None),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """List files under ``prefix`` *or* read one file at ``path``.

    Disambiguation: ``path`` wins if both are present. Both omitted →
    list at the thread root.

    Args:
        thread_id: URL segment — the thread whose files are scoped.
        prefix: Thread-relative folder prefix to list (e.g. ``input/``).
        path: Thread-relative single-file path to read.

    Returns:
        ``FileContent`` if ``path`` is given, else ``list[FileObject]``.
    """
    if path is not None:
        return await file_handler.read_file(
            enterprise.enterprise_id, thread_id, path, actor="user"
        )
    return await file_handler.list_files(
        enterprise.enterprise_id, thread_id, prefix or "", actor="user"
    )


@router.put(
    "/threads/{thread_id}/files",
    response_model=WriteResult,
    status_code=201,
)
async def write(
    thread_id: str,
    body: WriteFileRequest,
    path: str = Query(...),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """Write or replace one file from a JSON ``{content}`` body.

    Args:
        thread_id: URL segment — the thread whose files are scoped.
        body: Request body with the file's text content.
        path: Thread-relative destination path (required).

    Returns:
        ``WriteResult`` with the saved key and size.
    """
    return await file_handler.write_file(
        enterprise.enterprise_id, thread_id, path, body.content, actor="user"
    )


@router.post(
    "/threads/{thread_id}/files",
    response_model=list[WriteResult],
    status_code=201,
)
async def upload(
    thread_id: str,
    files: list[UploadFile],
    folder: str = Query(default="input/userUpload"),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """Multipart batch upload into ``folder``.

    Filenames from the upload parts are preserved verbatim; collisions
    overwrite. Default ``folder`` matches the paperclip drop convention.

    Args:
        thread_id: URL segment — the thread whose files are scoped.
        files: Multipart file parts.
        folder: Thread-relative destination folder.

    Returns:
        One ``WriteResult`` per saved file.
    """
    return await file_handler.upload_files(
        enterprise.enterprise_id, thread_id, folder, files, actor="user"
    )


@router.delete(
    "/threads/{thread_id}/files",
    status_code=204,
)
async def delete(
    thread_id: str,
    path: str = Query(...),
    enterprise: EnterpriseContext = Depends(get_enterprise_context),
):
    """Delete one file.

    Args:
        thread_id: URL segment — the thread whose files are scoped.
        path: Thread-relative path of the file to delete.
    """
    await file_handler.delete_file(
        enterprise.enterprise_id, thread_id, path, actor="user"
    )
