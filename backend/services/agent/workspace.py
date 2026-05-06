"""Workspace service — manages the checkout/commit lifecycle for agent runs.

Each agent run gets an isolated temp directory on local disk. Before the run,
existing workspace state is copied from persistent storage (S3). After the
run, modified files are synced back. The temp directory is always cleaned up.

Flow:
    temp_dir = await checkout(enterprise_id, thread_id)
    ... agent runs on temp_dir ...
    await commit(enterprise_id, thread_id, temp_dir)
    await cleanup(temp_dir)
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from backend.infra.registry import get_storage

logger = logging.getLogger(__name__)

# Standard subdirectories every workspace gets
WORKSPACE_SUBDIRS = ["input", "output", "reference", "workspace"]

# Subdirectories synced back to S3 on commit (input/ and reference/ are read-only)
COMMIT_SUBDIRS = ["workspace", "output"]


def _s3_workspace_prefix(enterprise_id: str, thread_id: str) -> str:
    """Build the S3 key prefix for a thread's workspace.

    Args:
        enterprise_id: Tenant identifier.
        thread_id: Conversation thread identifier.

    Returns:
        Relative path like ``enterprise/{eid}/workspaces/{tid}``.
    """
    return f"enterprise/{enterprise_id}/workspaces/{thread_id}"


def _sync_from_storage(s3_prefix: str, local_dir: Path) -> int:
    """Copy files from persistent storage to a local directory.

    Walks the storage tree under ``s3_prefix`` and recreates the directory
    structure under ``local_dir``.

    Args:
        s3_prefix: The S3 key prefix to copy from.
        local_dir: The local directory to copy into.

    Returns:
        Number of files copied.
    """
    storage = get_storage()
    abs_root = Path(storage.abs_path(s3_prefix))

    if not abs_root.exists():
        return 0

    count = 0
    for src_file in abs_root.rglob("*"):
        if not src_file.is_file():
            continue
        # Compute relative path from s3_prefix root
        rel = src_file.relative_to(abs_root)
        dest = local_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest)
        count += 1

    logger.info("Checked out %d files from %s", count, s3_prefix)
    return count


def _sync_to_storage(local_dir: Path, s3_prefix: str) -> int:
    """Copy files from a local directory to persistent storage.

    Walks ``local_dir`` and writes each file to the corresponding
    path under ``s3_prefix`` in storage.

    Args:
        local_dir: The local directory to copy from.
        s3_prefix: The S3 key prefix to copy into.

    Returns:
        Number of files synced.
    """
    storage = get_storage()

    if not local_dir.exists():
        return 0

    count = 0
    for src_file in local_dir.rglob("*"):
        if not src_file.is_file():
            continue
        rel = src_file.relative_to(local_dir)
        s3_key = f"{s3_prefix}/{rel}"
        storage.write(s3_key, src_file.read_bytes())
        count += 1

    logger.info("Committed %d files to %s", count, s3_prefix)
    return count


async def checkout(enterprise_id: str, thread_id: str) -> Path:
    """Create an isolated temp workspace and restore existing state from S3.

    Creates a temp directory with the standard subdirectories (input/,
    workspace/, output/, reference/).  If a previous workspace exists in
    S3 for this thread, its files are copied into the temp directory so the
    agent can continue where it left off.

    Args:
        enterprise_id: Tenant identifier (scopes the S3 path).
        thread_id: Conversation thread identifier.

    Returns:
        Path to the temp workspace root directory.
    """
    # --- Create isolated temp directory --------------------------------------
    temp_dir = Path(
        tempfile.mkdtemp(prefix=f"agent_{enterprise_id[:8]}_{thread_id[:8]}_")
    )
    for subdir in WORKSPACE_SUBDIRS:
        (temp_dir / subdir).mkdir()

    logger.info("Created temp workspace at %s", temp_dir)

    # --- Restore previous state from S3 if it exists -------------------------
    s3_prefix = _s3_workspace_prefix(enterprise_id, thread_id)
    _sync_from_storage(s3_prefix, temp_dir)

    return temp_dir


async def commit(enterprise_id: str, thread_id: str, temp_dir: Path) -> None:
    """Sync workspace/ and output/ from the temp directory back to S3.

    Only ``workspace/`` and ``output/`` are committed — ``input/`` and
    ``reference/`` are read-only and don't change during a run.

    Args:
        enterprise_id: Tenant identifier (scopes the S3 path).
        thread_id: Conversation thread identifier.
        temp_dir: Path to the temp workspace root directory.
    """
    s3_prefix = _s3_workspace_prefix(enterprise_id, thread_id)

    for subdir in COMMIT_SUBDIRS:
        local_subdir = temp_dir / subdir
        _sync_to_storage(local_subdir, f"{s3_prefix}/{subdir}")


async def cleanup(temp_dir: Path) -> None:
    """Remove the temp workspace directory.

    Safe to call even if the directory has already been removed.

    Args:
        temp_dir: Path to the temp workspace root directory.
    """
    shutil.rmtree(temp_dir, ignore_errors=True)
    logger.info("Cleaned up temp workspace at %s", temp_dir)
