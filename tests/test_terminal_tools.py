"""Integration test for terminal_tools sync flow.

Hits the real open-terminal container. Mocks storage and thread lookup so
it runs without MariaDB. Run with:
    uv run pytest tests/test_terminal_tools.py -s
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import sys
from unittest.mock import MagicMock

import pytest

# Stub out the services.agent package before terminal_tools is imported to
# break the circular import: terminal_tools → services.agent → langgraph_service
# → reporting_agent → terminal_tools.
_thread_stub = MagicMock()
_workspace_stub = MagicMock()
_workspace_stub.workspace_prefix = lambda enterprise_id, thread_id: f"enterprise/{enterprise_id}/workspaces/{thread_id}"
sys.modules.setdefault("backend.services.agent", MagicMock(thread=_thread_stub))
sys.modules.setdefault("backend.services.agent.thread", _thread_stub)
sys.modules.setdefault("backend.services.agent.workspace", _workspace_stub)

FAKE_PREFIX = "enterprise/test/workspaces/test-thread-001"
FAKE_THREAD_ID = "test-thread-001"
FAKE_CONFIG = {"configurable": {"thread_id": FAKE_THREAD_ID}}


class _FakeStorage:
    """In-memory storage stub."""

    def __init__(self):
        self._data: dict[str, bytes] = {}

    def list_objects(self, prefix: str):
        return [
            {"key": k}
            for k in self._data
            if k.startswith(prefix)
        ]

    def read(self, key: str) -> bytes:
        return self._data[key]

    def write(self, key: str, data: bytes):
        self._data[key] = data

    def write_text(self, key: str, text: str):
        self._data[key] = text.encode()

    def read_text(self, key: str) -> str:
        return self._data[key].decode()


@pytest.mark.asyncio
async def test_sync_round_trip():
    """Upload a file, run a command that creates another file, sync back."""
    import backend.ai.tools.terminal_tools as tt

    # Use a unique tmp dir so the test is isolated and doesn't collide with
    # anything else already on the container filesystem.
    import uuid
    container_workdir = f"/tmp/sprih-test-{uuid.uuid4().hex[:8]}"

    storage = _FakeStorage()
    storage.write_text(f"{FAKE_PREFIX}/input/hello.txt", "hello from s3\n")

    with (
        patch.object(tt, "get_workspace_path", new=AsyncMock(return_value=FAKE_PREFIX)),
        patch.object(tt, "get_storage", return_value=storage),
        patch.object(tt, "_CONTAINER_WORKDIR", container_workdir),
    ):
        # --- Step 1: upload workspace to container ---
        print("\n=== _sync_to_container ===")
        upload_result = await tt._sync_to_container(FAKE_CONFIG)
        print("result:", upload_result)
        assert "error" not in upload_result, upload_result
        assert upload_result["uploaded"], "nothing uploaded"

        container_dirs = upload_result["container_dirs"]
        print("container_dirs:", container_dirs)

        # --- Step 2: run a command that creates a new file in the same dir ---
        import os, requests
        base_url = os.getenv("OPEN_TERMINAL_URL", "http://localhost:8001")
        api_key = os.getenv("OPEN_TERMINAL_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"}

        target_dir = container_dirs[0]
        output_path = f"{target_dir}/output.txt"
        cmd = f"echo 'agent output' > '{output_path}'"
        print(f"\n=== Running command: {cmd} ===")
        resp = requests.post(
            f"{base_url}/execute",
            headers=headers,
            params={"wait": 15},
            json={"command": cmd},
            timeout=25,
        )
        print("execute status:", resp.status_code)
        print("execute response:", resp.json())

        # --- Step 3: sync container back to storage ---
        print("\n=== _sync_from_container ===")
        sync_result = await tt._sync_from_container(FAKE_CONFIG, container_dirs)
        print("result:", sync_result)
        assert "error" not in sync_result, sync_result

        # --- Step 4: verify storage contents ---
        print("\n=== Storage keys after sync ===")
        for key in storage._data:
            print(f"  {key!r}: {storage._data[key][:80]}")

        assert any("hello.txt" in k for k in storage._data), "original file missing"
        assert any("output.txt" in k for k in storage._data), "agent-created file not synced back"
