"""Terminal tools — agent-callable utilities for interacting with the open-terminal container."""

from __future__ import annotations

import base64
import os
from pathlib import Path, PurePosixPath

import requests
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

_BINARY_EXTENSIONS = {
    ".pdf", ".xlsx", ".xls", ".docx", ".doc", ".pptx", ".ppt",
    ".png", ".jpg", ".jpeg", ".gif", ".zip", ".tar", ".gz",
}

from backend.infra.registry import get_storage
from backend.services.agent import thread as thread_service
from backend.services.agent.workspace import workspace_prefix

BASE_URL = os.getenv("OPEN_TERMINAL_URL", "http://localhost:8001")
_API_KEY = os.getenv("OPEN_TERMINAL_API_KEY", "")
_AUTH_HEADERS = {"Authorization": f"Bearer {_API_KEY}"}
# Base directory inside the container; a per-thread subdirectory is appended
# at runtime so each thread's workspace is fully isolated from the rest of
# the container filesystem.
_CONTAINER_BASE = os.getenv("OPEN_TERMINAL_WORKDIR", "/workspace")
MAX_OUTPUT_CHARS = 8000


def _thread_workdir(thread_id: str) -> str:
    """Return the container-side working directory scoped to this thread.

    Args:
        thread_id: UUID of the conversation thread.

    Returns:
        Absolute container path of the form ``"{base}/{thread_id}"``.
    """
    return f"{_CONTAINER_BASE.rstrip('/')}/{thread_id}"


def _truncate_output(output: str, label: str = "Output") -> str:
    if len(output) <= MAX_OUTPUT_CHARS:
        return output
    half = MAX_OUTPUT_CHARS // 2
    return (
        output[:half]
        + f"\n\n... [{label} truncated — {len(output):,} chars total, showing first and last {half}] ...\n\n"
        + output[-half:]
    )


async def get_workspace_path(thread_id: str) -> str | None:
    """Return the S3 prefix for thread_id's workspace, or None if not found.

    Args:
        thread_id: UUID of the conversation thread.

    Returns:
        Storage prefix of the form
        ``"enterprise/{enterprise_id}/workspaces/{thread_id}"``,
        or ``None`` if the thread does not exist.
    """
    row = await thread_service.get(thread_id)
    if row is None:
        return None
    return workspace_prefix(row["enterprise_id"], thread_id)


async def _sync_to_container(config: RunnableConfig) -> dict:
    """Upload all files from the S3 workspace to the open-terminal container.

    Enumerates every object under the thread's workspace prefix via the storage
    adapter and POSTs each one to ``/files/upload``, preserving the relative
    folder structure under the thread-scoped container workdir
    (``{_CONTAINER_BASE}/{thread_id}``). Tracks which container directories
    were populated so the caller can scope the sync-back to those same dirs.

    Args:
        config: LangGraph runnable config carrying ``thread_id``.

    Returns:
        Dict with ``uploaded`` (list of relative paths), ``failed``
        (list of ``{path, error}`` dicts), ``container_dirs`` (sorted list
        of container directory paths that received at least one file), and
        ``workdir`` (the thread's container working directory).
        Returns ``{"error": ...}`` if the thread is not found.
    """
    thread_id: str = config["configurable"]["thread_id"]
    prefix = await get_workspace_path(thread_id)
    if prefix is None:
        return {"error": f"thread '{thread_id}' not found"}

    workdir = _thread_workdir(thread_id)
    storage = get_storage()
    objects = storage.list_objects(prefix)

    uploaded: list[str] = []
    failed: list[dict] = []
    container_dirs: set[str] = set()

    for obj in objects:
        key: str = obj["key"]
        rel_path = key[len(prefix):].lstrip("/")
        remote_dir = str(PurePosixPath(workdir) / Path(rel_path).parent.as_posix())
        container_dirs.add(remote_dir)
        try:
            content = storage.read(key)
            response = requests.post(
                f"{BASE_URL}/files/upload",
                headers=_AUTH_HEADERS,
                params={"directory": remote_dir},
                files={"file": (Path(rel_path).name, content, "application/octet-stream")},
                timeout=60,
            )
            response.raise_for_status()
            uploaded.append(rel_path)
        except requests.HTTPError as exc:
            failed.append({"path": rel_path, "error": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"})
        except Exception as exc:
            failed.append({"path": rel_path, "error": str(exc)})
    return {
        "uploaded": uploaded,
        "failed": failed,
        "container_dirs": sorted(container_dirs),
        "workdir": workdir,
    }


async def _sync_from_container(
    config: RunnableConfig,
    container_dirs: list[str],
    workdir: str,
    skip_rel_paths: set[str] | None = None,
) -> dict:
    """Download agent-created files from the container back to the S3 workspace.

    Runs ``find`` scoped to ``container_dirs``, reads each file via
    ``/files/read``, and writes it to ``{prefix}/{rel_path}`` in storage.
    Files listed in ``skip_rel_paths`` (the set uploaded by
    ``_sync_to_container``) are left untouched — this prevents the
    ``/files/read`` API from overwriting binary input files (e.g. PDFs)
    with corrupted content.

    Args:
        config: LangGraph runnable config carrying ``thread_id``.
        container_dirs: Container directory paths to scan (returned by
            ``_sync_to_container``).
        workdir: Thread-scoped container working directory (returned by
            ``_sync_to_container``). Used to strip the container prefix
            when computing workspace-relative storage keys.
        skip_rel_paths: Workspace-relative paths that were uploaded to the
            container and should not be synced back. Defaults to ``None``
            (sync everything, no skipping).

    Returns:
        Dict with ``saved`` (list of relative paths) and ``failed``
        (list of ``{path, error}`` dicts).
        Returns ``{"error": ...}`` if the thread is not found.
    """
    if not container_dirs:
        return {"saved": [], "failed": []}

    thread_id: str = config["configurable"]["thread_id"]
    prefix = await get_workspace_path(thread_id)
    if prefix is None:
        return {"error": f"thread '{thread_id}' not found"}

    storage = get_storage()
    saved: list[str] = []
    failed: list[dict] = []

    # --- List files only inside the workspace directories ---
    dirs_arg = " ".join(f'"{d}"' for d in container_dirs)
    find_resp = requests.post(
        f"{BASE_URL}/execute",
        headers=_AUTH_HEADERS,
        params={"wait": 30},
        json={"command": f"find {dirs_arg} -type f 2>/dev/null | sort"},
        timeout=40,
    )
    find_resp.raise_for_status()
    raw = "".join(item["data"] for item in find_resp.json().get("output", []))
    file_paths = [p.strip() for p in raw.splitlines() if p.strip()]

    # --- Read each file and write to storage ---
    workdir_prefix = workdir.rstrip("/") + "/"
    for abs_path in file_paths:
        rel_path = abs_path.removeprefix(workdir_prefix).lstrip("/")
        if not rel_path:
            continue
        if skip_rel_paths and rel_path in skip_rel_paths:
            continue
        try:
            file_resp = requests.get(
                f"{BASE_URL}/files/read",
                headers=_AUTH_HEADERS,
                params={"path": abs_path},
                timeout=60,
            )
            file_resp.raise_for_status()
            data = file_resp.json()
            content = data.get("content", "")
            storage_key = f"{prefix}/{rel_path}"
            if Path(rel_path).suffix.lower() in _BINARY_EXTENSIONS:
                try:
                    raw_bytes = base64.b64decode(content)
                except Exception:
                    raw_bytes = content.encode("utf-8")
                storage.write(storage_key, raw_bytes)
            else:
                storage.write_text(storage_key, content)
            saved.append(rel_path)
        except Exception as exc:
            failed.append({"path": rel_path, "error": str(exc)})

    return {"saved": saved, "failed": failed}


@tool
async def run_terminal_command(command: str, wait: int = 300, *, config: RunnableConfig) -> str:
    """Execute a shell command inside the open-terminal container and return its output.

    The command runs inside a thread-scoped sandbox directory
    (``{OPEN_TERMINAL_WORKDIR}/{thread_id}``) so the working directory is
    always the thread's own workspace. All paths in the command are relative
    to that workspace unless an absolute path is explicitly used.

    Before running the command the thread's full workspace is synced to the
    container. After the command completes, all files in those same container
    directories — including new or modified ones — are synced back to the
    workspace.

    Args:
        command: Shell command to run, e.g. ``"ls"`` or ``"python run.py"``.
        wait: Max seconds to wait for the command to finish.

    Returns:
        stdout/stderr output from the command, truncated if very large.
    """
    upload_result = await _sync_to_container(config)
    if "error" in upload_result:
        return upload_result

    workdir = upload_result["workdir"]
    # Scope the command to the thread workspace: create the directory if it
    # doesn't exist yet (first run) then cd into it before executing.
    sandboxed = f"mkdir -p '{workdir}' && cd '{workdir}' && ({command})"

    resp = requests.post(
        f"{BASE_URL}/execute",
        headers=_AUTH_HEADERS,
        params={"wait": wait},
        json={"command": sandboxed},
        timeout=wait + 10,
    )
    resp.raise_for_status()
    resp_data = resp.json()
    if resp_data.get("status") == "running":
        partial = "".join(item["data"] for item in resp_data.get("output", []))
        return (
            f"Command is still running after {wait}s (id: {resp_data.get('id', '?')}).\n"
            f"Call run_terminal_command again with a larger wait value to wait longer.\n"
            f"Partial output so far:\n{partial}"
        )
    output = "".join(item["data"] for item in resp_data.get("output", []))
    await _sync_from_container(
        config,
        upload_result["container_dirs"],
        workdir=workdir,
        skip_rel_paths=set(upload_result["uploaded"]),
    )
    return _truncate_output(output, label="Terminal output")
