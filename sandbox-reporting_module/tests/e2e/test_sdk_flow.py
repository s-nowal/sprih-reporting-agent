"""
E2E test simulating the exact call sequence the frontend SDK makes.

Exercises the full stack: FastAPI -> handlers -> LangGraph agent -> Claude
-> Tavily -> storage + DB. No mocking — catches integration bugs that only
surface when all layers are wired together.

Requires:
- Docker containers running (``docker compose up -d``)
- ``.env`` with ANTHROPIC_API_KEY, TAVILY_API_KEY

Flow tested (mirrors @langchain/langgraph-sdk client):
  1. GET  /info
  2. POST /assistants/search
  3. POST /threads
  4. POST /threads/{id}/runs/stream  (SSE)
  5. GET  /threads/{id}/state
  6. GET  /threads/{id}
  7. GET  /threads/{id}/runs/{run_id}
"""

from tests.utils.sse import parse_sse_events


class TestSingleTurnFlow:
    """Simulate a user opening the app and sending one message."""

    def test_full_conversation_lifecycle(self, client, auth_headers):
        """Walk through the complete SDK call sequence for a single-turn chat.

        Steps match the frontend's useChat hook and page.tsx initialization.
        Each step verifies the response shape the SDK expects.
        """

        # --- Step 1: GET /info (app startup check) ----------------------------
        resp = client.get("/info")
        assert resp.status_code == 200
        info = resp.json()
        assert "default_assistant" in info
        assert "version" in info

        # --- Step 2: POST /assistants/search (find the assistant) -------------
        # The frontend searches by its configured assistantId as graph_id.
        resp = client.post(
            "/assistants/search",
            json={"graph_id": "reporting-agent", "limit": 100},
        )
        assert resp.status_code == 200
        assistants = resp.json()
        assert len(assistants) >= 1, (
            "No assistant found for graph_id='reporting-agent'. "
            "Check ASSISTANTS dict in routers/assistants.py"
        )

        # SDK expects these fields on each assistant
        assistant = assistants[0]
        assert "assistant_id" in assistant
        assert "graph_id" in assistant
        assert "name" in assistant
        assert "metadata" in assistant
        assert assistant["metadata"].get("created_by") == "system"

        assistant_id = assistant["assistant_id"]

        # --- Step 3: POST /threads (create a conversation) --------------------
        resp = client.post("/threads", json={}, headers=auth_headers)
        assert resp.status_code == 201
        thread = resp.json()

        # SDK expects these fields
        assert "thread_id" in thread
        assert thread["status"] == "idle"
        assert "created_at" in thread
        assert "updated_at" in thread
        assert "metadata" in thread

        thread_id = thread["thread_id"]
        created_at = thread["created_at"]

        # --- Step 4: POST /threads/{id}/runs/stream (agent execution) ---------
        resp = client.post(
            f"/threads/{thread_id}/runs/stream",
            json={
                "assistant_id": assistant_id,
                "input": {
                    "messages": [
                        {
                            "type": "human",
                            "content": "What is ESG reporting? Answer in one sentence.",
                        }
                    ]
                },
                "stream_mode": "values",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Stream returned {resp.status_code}: {resp.text[:500]}"

        # Content-type should be SSE
        content_type = resp.headers.get("content-type", "")
        assert "text/event-stream" in content_type

        # Parse the SSE response
        events = parse_sse_events(resp.text)
        assert len(events) >= 3, (
            f"Expected at least 3 events (metadata, values, end), got {len(events)}: "
            f"{[e['event'] for e in events]}"
        )

        # First event: metadata with run_id and thread_id
        metadata_event = events[0]
        assert metadata_event["event"] == "metadata"
        assert "run_id" in metadata_event["data"]
        assert metadata_event["data"]["thread_id"] == thread_id
        run_id = metadata_event["data"]["run_id"]

        # Middle events: at least one "values" event with messages
        values_events = [e for e in events if e["event"] == "values"]
        assert len(values_events) >= 1, "Expected at least one values event"

        # Each values event should have a messages list of dicts (not raw LangChain objects)
        for ve in values_events:
            assert "messages" in ve["data"], f"Values event missing 'messages': {ve['data']}"
            messages = ve["data"]["messages"]
            assert isinstance(messages, list)
            for msg in messages:
                assert isinstance(msg, dict), f"Message should be a dict, got {type(msg)}"
                assert "type" in msg, f"Message missing 'type' field: {msg}"
                assert "content" in msg, f"Message missing 'content' field: {msg}"

        # Last values event should contain an AI response
        last_values = values_events[-1]
        last_messages = last_values["data"]["messages"]
        ai_messages = [m for m in last_messages if m["type"] == "ai" and m.get("content")]
        assert len(ai_messages) >= 1, "Expected at least one AI message with content"

        # Check for error events (should have none in happy path)
        error_events = [e for e in events if e["event"] == "error"]
        assert len(error_events) == 0, f"Unexpected error events: {error_events}"

        # Last event: end
        assert events[-1]["event"] == "end"

        # --- Step 5: GET /threads/{id}/state (SDK state hydration) ------------
        resp = client.get(
            f"/threads/{thread_id}/state",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        state = resp.json()

        # SDK expects {values, next, checkpoint}
        assert "values" in state
        assert "messages" in state["values"]
        assert len(state["values"]["messages"]) >= 2, (
            "Thread state should have at least the human message and AI response"
        )

        # --- Step 6: GET /threads/{id} (verify thread updated) ----------------
        resp = client.get(
            f"/threads/{thread_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        thread_after = resp.json()
        assert thread_after["status"] == "idle"
        assert thread_after["updated_at"] >= created_at, (
            "Thread updated_at should advance after a run"
        )

        # --- Step 7: GET /threads/{id}/runs/{run_id} (verify run status) ------
        resp = client.get(
            f"/threads/{thread_id}/runs/{run_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        run = resp.json()
        assert run["status"] == "success"
        assert run["thread_id"] == thread_id
