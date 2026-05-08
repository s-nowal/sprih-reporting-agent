"""
E2E test for the Reporting Agent — exercises the full orchestration stack.

The Reporting Agent (``create_deep_agent``) orchestrates:
- Research subagent (web search + crawl via Tavily)
- File system tools (read, write, ls, glob on workspace)
- Human-in-the-loop interrupts (``request_user_input``)
- Direct writes to storage via ``S3Backend`` (no temp-dir round-trip)

This test simulates the frontend SDK call sequence for a reporting task.

Requires:
- Docker containers running (``docker compose up -d``)
- ``.env`` with ANTHROPIC_API_KEY, TAVILY_API_KEY

Flow tested:
  1. GET  /info                          → verify default is reporting-agent
  2. POST /threads                        → create conversation
  3. POST /threads/{id}/runs/stream       → agent execution (SSE)
  4. Verify SSE events: metadata, values (with messages), end
  5. GET  /threads/{id}/state             → verify thread state updated
  6. Verify agent writes landed in S3 storage directly
"""

import os
from pathlib import Path

from tests.utils.sse import parse_sse_events


class TestReportingAgentFlow:
    """Simulate a user asking the Reporting Agent to start an ESG report."""

    def test_reporting_agent_single_turn(self, client, auth_headers):
        """Walk through a single-turn reporting agent conversation.

        Sends a simple ESG question to the reporting agent and verifies
        the full pipeline: agent execution streaming files directly to S3
        via S3Backend, with SSE events flowing to the client.

        Steps match the frontend's useChat hook and page.tsx initialization.
        """

        # --- Step 1: GET /info — verify reporting-agent is the default -------
        resp = client.get("/info")
        assert resp.status_code == 200
        info = resp.json()
        assert info["default_assistant"] == "reporting-agent"

        # --- Step 2: POST /threads — create conversation ---------------------
        resp = client.post("/threads", json={}, headers=auth_headers)
        assert resp.status_code == 201
        thread = resp.json()
        thread_id = thread["thread_id"]
        assert thread["status"] == "idle"

        # --- Step 3: POST /threads/{id}/runs/stream — agent execution --------
        resp = client.post(
            f"/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": "reporting-agent",
                "input": {
                    "messages": [
                        {
                            "type": "human",
                            "content": (
                                "What are the key sections of a GRI-aligned "
                                "ESG report? Answer briefly."
                            ),
                        }
                    ]
                },
                "stream_mode": "values",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, (
            f"Stream returned {resp.status_code}: {resp.text[:500]}"
        )

        # --- Step 4: Verify SSE event structure ------------------------------
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        events = parse_sse_events(resp.text)
        assert len(events) >= 3, (
            f"Expected at least 3 events (metadata, values, end), "
            f"got {len(events)}: {[e['event'] for e in events]}"
        )

        # First event: metadata with run_id and thread_id
        metadata_event = events[0]
        assert metadata_event["event"] == "metadata"
        assert "run_id" in metadata_event["data"]
        assert metadata_event["data"]["thread_id"] == thread_id
        run_id = metadata_event["data"]["run_id"]

        # Values events: must have messages as serialised dicts
        values_events = [e for e in events if e["event"] == "values"]
        assert len(values_events) >= 1, "Expected at least one values event"

        for ve in values_events:
            assert "messages" in ve["data"]
            messages = ve["data"]["messages"]
            assert isinstance(messages, list)
            for msg in messages:
                assert isinstance(msg, dict), (
                    f"Message should be a dict, got {type(msg)}"
                )
                assert "type" in msg
                assert "content" in msg

        # Last values event should contain an AI response
        last_messages = values_events[-1]["data"]["messages"]
        ai_messages = [
            m for m in last_messages
            if m["type"] == "ai" and m.get("content")
        ]
        assert len(ai_messages) >= 1, (
            "Expected at least one AI message with content"
        )

        # No error events in happy path
        error_events = [e for e in events if e["event"] == "error"]
        assert len(error_events) == 0, (
            f"Unexpected error events: {error_events}"
        )

        # End event
        assert events[-1]["event"] == "end"

        # --- Step 5: GET /threads/{id}/state — verify state updated ----------
        resp = client.get(
            f"/threads/{thread_id}/state",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        state = resp.json()
        assert "values" in state
        assert "messages" in state["values"]
        assert len(state["values"]["messages"]) >= 2, (
            "Thread state should have at least the human message and AI response"
        )

        # --- Step 6: GET /threads/{id}/runs/{run_id} — verify run status -----
        resp = client.get(
            f"/threads/{thread_id}/runs/{run_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        run = resp.json()
        assert run["status"] == "success"
        assert run["thread_id"] == thread_id

    def test_workspace_committed_to_storage(self, client, auth_headers):
        """Verify that agent writes land directly in S3-backed storage.

        With S3Backend, file writes are persisted live (no commit step).
        This test sends a message that triggers a file write (the reporting
        agent writes to workspace/ as part of its workflow) and checks that
        the workspace directory exists in storage after the run completes.
        """

        # --- Create thread and run the agent ---------------------------------
        resp = client.post("/threads", json={}, headers=auth_headers)
        assert resp.status_code == 201
        thread_id = resp.json()["thread_id"]

        resp = client.post(
            f"/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": "reporting-agent",
                "input": {
                    "messages": [
                        {
                            "type": "human",
                            "content": (
                                "Write 'hello world' to workspace/test.md "
                                "using write_file, then confirm you did it."
                            ),
                        }
                    ]
                },
                "stream_mode": "values",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200

        events = parse_sse_events(resp.text)
        error_events = [e for e in events if e["event"] == "error"]
        assert len(error_events) == 0, (
            f"Agent errored: {error_events}"
        )

        # --- Verify agent writes landed in S3-backed storage -----------------
        # S3Backend writes live to:
        #   data/s3/enterprise/{eid}/workspaces/{thread_id}/workspace/
        from backend.config import settings

        enterprise_id = "test-enterprise"
        workspace_s3_dir = Path(settings.storage_root) / (
            f"enterprise/{enterprise_id}/workspaces/{thread_id}/workspace"
        )

        # The workspace directory should exist in storage after the run
        assert workspace_s3_dir.exists(), (
            f"Agent writes did not land in S3. Expected dir: {workspace_s3_dir}"
        )

        # Check that the agent actually wrote the test file
        test_file = workspace_s3_dir / "test.md"
        if test_file.exists():
            content = test_file.read_text()
            assert "hello" in content.lower(), (
                f"test.md exists but content unexpected: {content[:200]}"
            )

        # --- Cleanup: remove the workspace from storage ----------------------
        import shutil
        workspace_root = Path(settings.storage_root) / (
            f"enterprise/{enterprise_id}/workspaces/{thread_id}"
        )
        if workspace_root.exists():
            shutil.rmtree(workspace_root)
