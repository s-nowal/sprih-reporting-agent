"""E2E test for ConOps §2.1 — First message on a fresh thread.

Spec source: ``docs/ConOps.md`` §2.1.

Walks the API call sequence the spec prescribes and asserts every write that
should follow against MariaDB, S3-backed storage, and the SSE stream. One
test, one ConOps step.

Spec recap:

    Trigger: user types her first message and sends.

    API calls (in order):
      1. POST /threads {}                        ← satisfied by ``fresh_thread`` fixture
      2. POST /threads/{thread_id}/runs/stream
         body: {assistant_id, input: {messages: [{type: "human", content}]}}

    Writes:
      On POST /threads:
        - threads INSERT (status='idle', metadata.title unset)
        - S3 scaffold input/userUpload/.keep, output/.keep
      On run start:
        - jobs INSERT (status='running')
        - threads UPDATE: status idle → busy
      During stream (per agent node-step):
        - LangGraph checkpointer APPEND
      On stream end (success):
        - jobs UPDATE: status → completed
        - threads UPDATE: status → idle, metadata.title=<generated>
      SSE events: metadata → values… → end (no error)

The thread-creation half of §2.1 is exercised through the ``fresh_thread``
fixture (whose post-conditions this test asserts on) so downstream tests
(§2.2, §2.3, ...) can reuse the same fixture. The runs/stream half is
driven directly here since it's what makes §2.1 distinctive vs. §2.4.

Requires:
  - Docker containers running (``docker compose up -d``)
  - .env with ANTHROPIC_API_KEY
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.job import Job
from backend.models.thread import Thread
from tests.e2e.conftest import ENTERPRISE_ID
from tests.utils.sse import parse_sse_events


async def test_section_2_1_first_message_on_fresh_thread(
    client, auth_headers, fresh_thread, db_session: AsyncSession
):
    """Walk ConOps §2.1 end-to-end and verify every prescribed write.

    Phases:
      1. fresh_thread fixture state — response shape, threads row, S3 scaffold.
      2. POST /threads/{tid}/runs/stream — SSE stream, jobs row, run-end state.
      3. GET /threads/{tid}/state — values persisted from the final stream state.
    """

    thread_id = fresh_thread["thread_id"]
    workspace_root = fresh_thread["workspace_root"]
    create_response = fresh_thread["create_response"]

    # =========================================================================
    # Phase 1 — POST /threads post-conditions (driven by fresh_thread fixture)
    # Spec: bootstrap the thread row and scaffold the S3 workspace.
    # =========================================================================

    # --- Response shape ------------------------------------------------------
    assert create_response["status"] == "idle", (
        f"New thread should land in status='idle', "
        f"got {create_response['status']!r}"
    )
    # enterprise_id lives on the threads.enterprise_id column, not in
    # metadata; asserted against the DB row below.

    # --- DB write: threads row inserted --------------------------------------
    row = (
        await db_session.execute(
            select(Thread).where(Thread.thread_id == thread_id)
        )
    ).scalar_one_or_none()
    assert row is not None, "threads row should exist after POST /threads"
    assert row.enterprise_id == ENTERPRISE_ID
    assert row.status == "idle"
    # Spec: title is persisted on threads.metadata['title']. On a fresh thread
    # before any run, the metadata holds nothing (it's empty).
    assert "title" not in (row.metadata_ or {}), (
        "metadata['title'] should be unset before the first run completes"
    )

    # --- S3 write: scaffold .keep files --------------------------------------
    input_keep = workspace_root / "input" / "userUpload" / ".keep"
    output_keep = workspace_root / "output" / ".keep"
    assert input_keep.exists(), f"Spec requires scaffold; missing: {input_keep}"
    assert output_keep.exists(), f"Spec requires scaffold; missing: {output_keep}"

    # =========================================================================
    # Phase 2 — POST /threads/{tid}/runs/stream
    # Spec: insert jobs row (running), stream agent, finalise jobs row.
    # =========================================================================
    first_message = (
        "Help me draft the Scope 3 emissions section for Acme's Q3 2025 "
        "sustainability report. Keep it brief — two short paragraphs."
    )

    resp = client.post(
        f"/threads/{thread_id}/runs/stream",
        json={
            "assistant_id": "reporting-agent",
            "input": {
                "messages": [{"type": "human", "content": first_message}]
            },
            "stream_mode": "values",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, (
        f"runs/stream returned {resp.status_code}: {resp.text[:300]}"
    )
    assert "text/event-stream" in resp.headers.get("content-type", "")

    # --- SSE event order: metadata → values… → end (no error) ---------------
    events = parse_sse_events(resp.text)
    event_names = [e["event"] for e in events]
    assert len(events) >= 3, (
        f"Expected at least metadata + values + end, got {event_names}"
    )

    assert events[0]["event"] == "metadata", (
        f"First SSE event should be 'metadata', got {events[0]['event']!r}"
    )
    assert events[0]["data"]["thread_id"] == thread_id
    assert "run_id" in events[0]["data"]

    values_events = [e for e in events if e["event"] == "values"]
    assert len(values_events) >= 1, "Expected at least one 'values' event"

    final_messages = values_events[-1]["data"]["messages"]
    ai_msgs = [
        m for m in final_messages
        if m.get("type") == "ai" and m.get("content")
    ]
    assert len(ai_msgs) >= 1, (
        "Final 'values' event should carry at least one AI message; "
        f"got message types: {[m.get('type') for m in final_messages]}"
    )

    error_events = [e for e in events if e["event"] == "error"]
    assert error_events == [], f"Unexpected error events: {error_events}"

    assert events[-1]["event"] == "end", (
        f"Last SSE event should be 'end', got {events[-1]['event']!r}"
    )

    # --- DB write: exactly one jobs row, finalised to 'completed' -----------
    # Roll back to release the REPEATABLE READ snapshot before re-reading;
    # the new rows were committed by a different session.
    await db_session.rollback()
    jobs = (
        await db_session.execute(
            select(Job).where(Job.thread_id == thread_id)
        )
    ).scalars().all()
    assert len(jobs) == 1, (
        f"Expected exactly one jobs row for this thread, got {len(jobs)}: "
        f"{[(j.id, j.status) for j in jobs]}"
    )
    job = jobs[0]
    assert job.status == "completed", (
        f"Spec: jobs.status should transition running → completed at "
        f"stream end; got {job.status!r}"
    )
    assert job.job_type == "reporting-agent"
    assert job.enterprise_id == ENTERPRISE_ID

    # --- DB write: threads row at run end ------------------------------------
    t_after = (
        await db_session.execute(
            select(Thread).where(Thread.thread_id == thread_id)
        )
    ).scalar_one()
    # Spec: status returns to 'idle' at run end (handler set it to 'busy'
    # on run start and back to 'idle' on stream-end success).
    assert t_after.status == "idle", (
        f"Spec: threads.status should be 'idle' at run end; "
        f"got {t_after.status!r}"
    )
    # Spec: values now contain the serialised message list. The handler
    # writes this via thread_service.update_values at stream end.
    assert t_after.values is not None
    persisted = t_after.values.get("messages") or []
    assert len(persisted) >= 2, (
        f"threads.values.messages should hold the user message and the "
        f"agent reply; got {len(persisted)}"
    )
    # Spec: first-message side-effect — title generated from the user message
    # and persisted to threads.metadata['title'].
    title = (t_after.metadata_ or {}).get("title")
    assert title and title.strip(), (
        "Spec: title should be generated from the first user message and "
        f"persisted to metadata['title']; got metadata={t_after.metadata_!r}"
    )

    # =========================================================================
    # Phase 3 — GET /threads/{tid}/state
    # Spec: returns the values persisted at stream end.
    # =========================================================================
    resp = client.get(f"/threads/{thread_id}/state", headers=auth_headers)
    assert resp.status_code == 200
    state = resp.json()
    msgs = state["values"]["messages"]
    assert len(msgs) >= 2, (
        f"GET /state should return user + AI messages; got {len(msgs)}"
    )
