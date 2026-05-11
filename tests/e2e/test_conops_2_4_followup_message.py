"""E2E test for ConOps §2.4 — Send a follow-up message on an existing thread.

Spec source: ``docs/ConOps.md`` §2.4.

Sends a second user message into a thread that already has §2.1's run on
it. Verifies the run lifecycle repeats (jobs row, status flip, checkpoint
append, values update) AND that the first-message-only side-effect (title
generation) is NOT re-triggered.

Spec recap:

    Trigger: user types a follow-up and sends.

    API call:
      - POST /threads/{thread_id}/runs/stream
        body: {assistant_id, input: {messages: [{type: "human", content}]}}

    Writes:
      On run start:
        - jobs INSERT (status='running')
        - threads UPDATE: status: idle → busy
      During stream (per node-step):
        - LangGraph checkpointer APPEND
      On stream end:
        - jobs UPDATE: status → completed (or failed)
        - threads UPDATE: status → idle (or error). Title remains as set in §2.1.

Requires:
  - Docker containers running (``docker compose up -d``)
  - .env with ANTHROPIC_API_KEY (consumed by the ``thread_with_history`` fixture)
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.job import Job
from backend.models.thread import Thread
from tests.utils.sse import parse_sse_events


async def test_section_2_4_followup_message(
    client, auth_headers, thread_with_history, db_session: AsyncSession
):
    """Drive a follow-up run and verify the prescribed writes.

    The fixture has already left the thread in post-§2.1 state with one
    completed jobs row and the title set. This test sends a second message
    and asserts the jobs row count goes to 2, the title is unchanged, and
    the new message exchange has been appended to ``threads.values``.
    """
    thread_id = thread_with_history["thread_id"]

    # =========================================================================
    # Snapshot pre-follow-up state — for diff assertions below.
    # =========================================================================
    row_before = (
        await db_session.execute(
            select(Thread).where(Thread.thread_id == thread_id)
        )
    ).scalar_one()
    title_before = (row_before.metadata_ or {}).get("title")
    messages_before = (row_before.values or {}).get("messages") or []
    assert title_before, "Spec precondition: title should be set after §2.1"
    assert len(messages_before) >= 2, (
        "Spec precondition: post-§2.1 thread should hold user + AI messages"
    )

    jobs_before = (
        await db_session.execute(
            select(Job).where(Job.thread_id == thread_id)
        )
    ).scalars().all()
    assert len(jobs_before) == 1, (
        f"Spec precondition: §2.1 should have created exactly one jobs row; "
        f"got {len(jobs_before)}"
    )

    # =========================================================================
    # API call: send the follow-up message
    # =========================================================================
    followup = (
        "Pick one of those categories and name the two most useful data "
        "points to request from a supplier. One sentence each."
    )
    resp = client.post(
        f"/threads/{thread_id}/runs/stream",
        json={
            "assistant_id": "reporting-agent",
            "input": {"messages": [{"type": "human", "content": followup}]},
            "stream_mode": "values",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 200, (
        f"runs/stream returned {resp.status_code}: {resp.text[:300]}"
    )
    assert "text/event-stream" in resp.headers.get("content-type", "")

    # --- SSE shape: metadata → values… → end (no error) ---------------------
    events = parse_sse_events(resp.text)
    event_names = [e["event"] for e in events]
    assert events[0]["event"] == "metadata", (
        f"First event should be 'metadata'; got {event_names[:3]}"
    )
    assert events[0]["data"]["thread_id"] == thread_id
    assert events[-1]["event"] == "end", (
        f"Last event should be 'end'; got {event_names[-3:]}"
    )
    assert [e for e in events if e["event"] == "error"] == [], (
        "Spec: no error events on the happy path"
    )

    # =========================================================================
    # DB writes — release REPEATABLE READ snapshot before re-reading
    # =========================================================================
    await db_session.rollback()

    # --- jobs: exactly two rows now, the second one 'completed' -------------
    jobs_after = (
        await db_session.execute(
            select(Job).where(Job.thread_id == thread_id)
        )
    ).scalars().all()
    assert len(jobs_after) == 2, (
        f"Spec: each run inserts one jobs row; expected 2 after the "
        f"follow-up, got {len(jobs_after)}"
    )
    new_jobs = [j for j in jobs_after if j.id not in {jobs_before[0].id}]
    assert len(new_jobs) == 1
    new_job = new_jobs[0]
    assert new_job.status == "completed", (
        f"Spec: follow-up jobs row should reach 'completed'; got {new_job.status!r}"
    )
    assert new_job.job_type == "reporting-agent"

    # --- threads: status back to idle, title unchanged, values grew ---------
    row_after = (
        await db_session.execute(
            select(Thread).where(Thread.thread_id == thread_id)
        )
    ).scalar_one()
    assert row_after.status == "idle", (
        f"Spec: threads.status should return to 'idle' after follow-up; "
        f"got {row_after.status!r}"
    )
    title_after = (row_after.metadata_ or {}).get("title")
    assert title_after == title_before, (
        f"Spec: title is a first-message-only side-effect; should not change "
        f"on the follow-up. before={title_before!r}, after={title_after!r}"
    )
    messages_after = (row_after.values or {}).get("messages") or []
    assert len(messages_after) > len(messages_before), (
        f"Spec: values.messages should grow with the follow-up; "
        f"before={len(messages_before)}, after={len(messages_after)}"
    )
    # The follow-up content must appear in the persisted message list.
    serialized = " ".join(
        m.get("content", "") for m in messages_after if isinstance(m, dict)
    )
    assert followup[:40] in serialized, (
        "Spec: the follow-up user message should be persisted into values"
    )
