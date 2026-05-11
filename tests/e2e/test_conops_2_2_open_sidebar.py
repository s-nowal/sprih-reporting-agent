"""E2E test for ConOps §2.2 — Open conversation history sidebar.

Spec source: ``docs/ConOps.md`` §2.2.

Drives the sidebar-list endpoint and asserts it returns the user's threads
with the post-§2.1 title visible. Uses the ``thread_with_history`` fixture to
land in the journey state §2.2 assumes (a thread that already had a first
message run through it, so ``metadata['title']`` is populated).

Spec recap:

    Trigger: Sara opens the sidebar.

    API call:
      - GET /threads
        Response: [{thread_id, title, status, updated_at, mirror: {...} | null}, ...]

    Effect: returns the user's threads. For threads with a thread_mirror_mappings
    row, the response includes the live folder name read from the provider.

Implementation notes vs spec:
  - The actual endpoint is ``POST /threads/search`` (with ``GET /threads/all``
    as an undocumented alias). The ConOps "GET /threads" is the Agent Protocol
    convention and a future cleanup item; the test drives the endpoint that
    exists today.
  - The response uses the standard ``ThreadResponse`` shape: title lives in
    ``metadata['title']`` rather than as a top-level field, and there's no
    ``mirror`` object yet. Both gaps are flagged inline.

Requires:
  - Docker containers running (``docker compose up -d``)
  - .env with ANTHROPIC_API_KEY (consumed by the ``thread_with_history`` fixture)
"""

from __future__ import annotations


async def test_section_2_2_open_conversation_history_sidebar(
    client, auth_headers, thread_with_history
):
    """Verify the sidebar-list call returns the post-§2.1 thread cleanly.

    The fixture has already driven §2.1 to completion against this thread;
    this test focuses purely on the sidebar fetch the user makes when they
    come back to the product later.
    """
    seeded_thread_id = thread_with_history["thread_id"]

    # =========================================================================
    # API call: list threads for the user (sidebar fetch)
    # =========================================================================
    resp = client.post("/threads/search", json={}, headers=auth_headers)
    assert resp.status_code == 200, (
        f"POST /threads/search returned {resp.status_code}: {resp.text[:300]}"
    )

    payload = resp.json()
    assert isinstance(payload, list), (
        f"Sidebar list should be a JSON array; got {type(payload).__name__}"
    )

    # =========================================================================
    # The seeded thread must appear in the list with title + idle status
    # =========================================================================
    matches = [t for t in payload if t["thread_id"] == seeded_thread_id]
    assert len(matches) == 1, (
        f"Seeded thread {seeded_thread_id!r} should appear exactly once in "
        f"the sidebar list; got {len(matches)} matches out of {len(payload)} "
        f"total threads"
    )
    item = matches[0]

    # --- Title is populated post-§2.1 (lives in metadata for now) -----------
    title = (item.get("metadata") or {}).get("title")
    assert title and title.strip(), (
        f"Sidebar entry should carry the generated title in metadata['title'] "
        f"after §2.1 completes; got metadata={item.get('metadata')!r}"
    )

    # --- Run finished, thread is back to idle --------------------------------
    assert item["status"] == "idle", (
        f"Spec: thread.status should be 'idle' after the §2.1 run; "
        f"got {item['status']!r}"
    )

    # --- updated_at is present (used by the sidebar to sort recents) --------
    assert item.get("updated_at"), (
        "Spec: each sidebar entry needs updated_at for recents-ordering"
    )

    # =========================================================================
    # Spec gaps (current implementation does not yet expose these):
    # =========================================================================
    # - Top-level ``title`` field on the response: today it's nested in
    #   metadata. When the response model surfaces title at the top level,
    #   replace the metadata lookup above with: ``assert item['title']``.
    # - ``mirror`` object on the response: today threads with a
    #   thread_mirror_mappings row don't surface the live folder name in
    #   this list response. When that lands, add an assertion that mirrored
    #   threads carry ``item['mirror'] == {'folder_name': ..., 'status': ...}``.
    # Both are flagged in §2.2 for follow-up.
