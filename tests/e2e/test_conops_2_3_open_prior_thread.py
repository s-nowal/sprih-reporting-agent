"""E2E test for ConOps §2.3 — Open a prior thread.

Spec source: ``docs/ConOps.md`` §2.3.

Drives the state-read endpoint and asserts it returns the persisted
conversation values from a thread that's already had a run.

Spec recap:

    Trigger: Sara clicks a thread in the sidebar.

    API call:
      - GET /threads/{thread_id}/state
        Response: {values: {messages: [...]}, status, ...}

    Effect: returns the latest checkpoint values for this thread.

Requires:
  - Docker containers running (``docker compose up -d``)
  - .env with ANTHROPIC_API_KEY (consumed by the ``thread_with_history`` fixture)
"""

from __future__ import annotations


async def test_section_2_3_open_prior_thread(
    client, auth_headers, thread_with_history
):
    """Verify ``GET /state`` returns the values persisted by §2.1's run."""
    thread_id = thread_with_history["thread_id"]

    resp = client.get(
        f"/threads/{thread_id}/state", headers=auth_headers
    )
    assert resp.status_code == 200, (
        f"GET /state returned {resp.status_code}: {resp.text[:300]}"
    )

    state = resp.json()
    assert "values" in state, f"Response missing 'values' key: {state.keys()}"
    messages = state["values"].get("messages") or []

    # --- Conversation has been restored end-to-end ---------------------------
    assert len(messages) >= 2, (
        f"Spec: state should hold at least the user message and the agent "
        f"reply from §2.1; got {len(messages)} messages"
    )

    # --- Messages are serialised dicts the UI can render ---------------------
    types = [m.get("type") for m in messages if isinstance(m, dict)]
    assert "human" in types, (
        f"Spec: state should include the user's first message; types={types}"
    )
    assert "ai" in types, (
        f"Spec: state should include the agent's reply; types={types}"
    )
