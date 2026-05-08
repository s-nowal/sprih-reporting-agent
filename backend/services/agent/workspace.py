"""Workspace addressing — the storage key prefix used per (enterprise, thread).

Historically this module also handled a temp-dir checkout/commit cycle: the
agent ran on local disk and we synced files to ``LocalStorage`` before and
after each run. With the introduction of ``S3Backend`` the agent now writes
to storage directly, so all that machinery is gone. The single remaining
responsibility is computing the storage key prefix that scopes a thread's
files; ``S3Backend`` and ``mirror.base`` both rely on this exact layout.
"""

from __future__ import annotations


def workspace_prefix(enterprise_id: str, thread_id: str) -> str:
    """Return the storage key prefix for a thread's workspace.

    The prefix is the namespace under which all of a thread's
    ``input/output/reference/workspace`` files live.

    Args:
        enterprise_id: Tenant identifier.
        thread_id: Conversation thread identifier.

    Returns:
        A storage-relative path of the form
        ``"enterprise/{enterprise_id}/workspaces/{thread_id}"``.
    """
    return f"enterprise/{enterprise_id}/workspaces/{thread_id}"
