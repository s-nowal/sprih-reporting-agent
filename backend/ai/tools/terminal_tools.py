"""Terminal tools — agent-callable utilities for interacting with the open-terminal container."""

from __future__ import annotations

import base64
import os
from pathlib import Path

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
# Base directory inside the container where files land; must be writable by the container user.
_CONTAINER_WORKDIR = os.getenv("OPEN_TERMINAL_WORKDIR", "/tmp/workspace")
MAX_OUTPUT_CHARS = 8000

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

@tool
async def upload_full_directory(*, config: RunnableConfig) -> dict:
    """Upload all files in the current thread's workspace to the open-terminal container.

    Enumerates every file under the thread's S3 workspace prefix (input,
    output, workspace, reference sub-directories) via the storage adapter and
    POSTs each one to the open-terminal ``/files/upload`` endpoint, preserving
    the relative folder structure.

    Returns:
        Dict with keys ``uploaded`` (list of relative paths that succeeded),
        ``failed`` (list that errored), ``total_uploaded``, ``total_failed``.
    """
    thread_id: str = config["configurable"]["thread_id"]
    prefix = await get_workspace_path(thread_id)
    if prefix is None:
        return {"error": f"thread '{thread_id}' not found"}
    storage = get_storage()
    objects = storage.list_objects(prefix)

    uploaded: list[str] = []
    failed: list[dict] = []

    for obj in objects:
        key: str = obj["key"]
        # Derive path relative to the workspace root (strip the S3 prefix)
        rel_path = key[len(prefix):].lstrip("/")
        remote_dir = _CONTAINER_WORKDIR + "/" + Path(rel_path).parent.as_posix()

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
        "container_workdir": _CONTAINER_WORKDIR,
        "uploaded": uploaded,
        "failed": failed,
        "total_uploaded": len(uploaded),
        "total_failed": len(failed),
    }

@tool
def run_terminal_command(command: str, wait: int = 300) -> str:
    """Execute any shell command inside the open-terminal container and return its output.

        :param command: Shell command to run, e.g. "ls /tmp", "cat /tmp/output.csv", "bash /tmp/run.sh"
        :type command: str

        :param wait: Max seconds to wait for the command to finish.
        :type wait: int

        :return: stdout/stderr output from the command.
        :rtype: str
    """
    resp = requests.post(
        f"{BASE_URL}/execute",
        headers=_AUTH_HEADERS,
        params={"wait": wait},
        json={"command": command},
        timeout=wait + 10,
    )
    resp.raise_for_status()
    output = resp.json().get("output", "")
    return _truncate_output(output, label='Terminal output')

@tool
async def add_file_to_local(env_path: str, local_filename: str, *, config: RunnableConfig) -> str:
    """Fetch a file from open-terminal and save it to the thread's workspace/parsed directory.

    Reads the file at ``env_path`` from the open-terminal container and writes
    it into ``{workspace}/workspace/parsed/{local_filename}`` via the storage
    adapter. Binary files (PDF, XLSX, etc.) are base64-decoded before writing.

    Args:
        env_path: Path inside the open-terminal container, e.g. ``"/output.md"``.
        local_filename: Filename to use when saving into the workspace.

    Returns:
        A success string with the storage path, or an error string on failure.
    """
    resp = requests.get(f"{BASE_URL}/files/read", headers=_AUTH_HEADERS, params={"path": env_path})
    try:
        data = resp.json()
    except Exception:
        return f"Error: Invalid JSON response | status={resp.status_code} | body={resp.text}"

    if resp.status_code != 200:
        return f"Error: Request failed | status={resp.status_code} | response={data}"

    if "content" not in data:
        return f"Error: 'content' missing in response | response={data}"

    thread_id: str = config["configurable"]["thread_id"]
    prefix = await get_workspace_path(thread_id)
    if prefix is None:
        return f"Error: thread '{thread_id}' not found"

    storage_key = f"{prefix}/output/{local_filename}"
    content = data["content"]

    if Path(local_filename).suffix.lower() in _BINARY_EXTENSIONS:
        try:
            raw = base64.b64decode(content)
        except ValueError:
            raw = content.encode("utf-8")
        get_storage().write(storage_key, raw)
    else:
        get_storage().write_text(storage_key, content)

    return f"Success: File saved to /workspace/parsed/{local_filename}"