"""Run handler — orchestrates agent execution and SSE streaming.

Replaces the original in-memory stub with real LangGraph agent execution.
Thread state (``_threads`` dict) is kept in sync with agent state after
each run so the HTTP-level ``GET /threads/{id}/state`` returns fresh data.
"""

import json
import logging
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from backend.handlers.thread_handler import _assert_ownership, _ensure_thread
from backend.schemas.runs import RunCreate, RunResponse
from backend.security.auth import EnterpriseContext
from backend.services import job as job_service
from backend.services.agent import get_agent_service
from backend.services.agent import thread as thread_service
from backend.services.agent import workspace as workspace_service

logger = logging.getLogger(__name__)

# In-memory store — replaced by RunService + DB later
_runs: dict[str, dict] = {}


def _to_response(r: dict) -> RunResponse:
    """Convert an internal run dict to a Pydantic ``RunResponse``."""
    return RunResponse(**r)


def _serialize_messages(messages: list) -> list[dict]:
    """Convert LangChain BaseMessage objects to JSON-serialisable dicts.

    LangGraph ``astream(stream_mode="values")`` yields state where
    ``messages`` contains ``BaseMessage`` subclasses. These are not
    JSON-serialisable — ``json.dumps`` would fail. This helper converts
    each message to a plain dict the frontend can consume.

    Handles both plain dicts (already serialised) and LangChain message
    objects (``HumanMessage``, ``AIMessage``, ``ToolMessage``).

    Args:
        messages: List of LangChain ``BaseMessage`` objects or plain dicts.

    Returns:
        List of dicts, each with at least ``type``, ``id``, ``content``.
        AI messages may also have ``tool_calls``. Tool messages have
        ``tool_call_id`` and ``name``.
    """
    result = []
    for msg in messages:
        if isinstance(msg, dict):
            result.append(msg)
            continue
        d: dict = {
            "type": msg.type,
            "id": msg.id or str(uuid4()),
            "content": msg.content,
        }
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            d["tool_calls"] = [
                {"id": tc["id"], "name": tc["name"], "args": tc["args"]}
                for tc in msg.tool_calls
            ]
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            d["tool_call_id"] = msg.tool_call_id
        if hasattr(msg, "name") and msg.name:
            d["name"] = msg.name
        result.append(d)
    return result


async def create_run(
    thread_id: str, data: RunCreate, enterprise: EnterpriseContext
) -> RunResponse:
    """Create a run record (non-streaming). Kept for API compatibility."""
    await _assert_ownership(thread_id, enterprise)
    now = datetime.now(timezone.utc)
    run_id = str(uuid4())

    r = {
        "run_id": run_id,
        "thread_id": thread_id,
        "assistant_id": data.assistant_id,
        "created_at": now,
        "updated_at": now,
        "status": "pending",
        "metadata": data.metadata or {},
    }
    _runs[run_id] = r
    return _to_response(r)


async def stream_run(
    thread_id: str,
    data: RunCreate,
    enterprise: EnterpriseContext,
    *,
    run_id: str,
) -> AsyncGenerator[dict, None]:
    """Stream real agent execution as SSE events.

    Orchestration flow:
    1. Record the run in the in-memory ``_runs`` store.
    2. Create a ``jobs`` row in MariaDB for provenance tracking.
    3. Delegate to ``LangGraphAgentService.stream()`` which runs the agent.
    4. For each state yielded by the graph, serialise messages and yield
       an SSE ``values`` event.
    5. On completion, sync the final messages back to the in-memory
       ``_threads`` store so ``GET /threads/{id}/state`` is up-to-date.
    6. On error, yield an SSE ``error`` event and mark the job as failed.

    Yields dicts compatible with ``sse-starlette``'s ``EventSourceResponse``:
    ``{"event": "<name>", "data": "<json-string>"}``

    Args:
        thread_id: The conversation thread to run against.
        data: ``RunCreate`` schema with ``input``, ``assistant_id``,
            and optional ``command`` for interrupt resume.
        enterprise: Authenticated tenant context from JWT / dev header.
        run_id: Pre-generated UUID (created by the router for the
            ``Content-Location`` header).

    Yields:
        SSE event dicts: ``metadata`` → N × ``values`` → ``end``
        (or ``error`` → ``end`` on failure).
    """
    await _ensure_thread(thread_id, enterprise)
    now = datetime.now(timezone.utc)

    _runs[run_id] = {
        "run_id": run_id,
        "thread_id": thread_id,
        "assistant_id": data.assistant_id,
        "created_at": now,
        "updated_at": now,
        "status": "running",
        "metadata": data.metadata or {},
    }

    # --- Metadata event (required by SDK) ------------------------------------
    yield {
        "event": "metadata",
        "data": json.dumps({"run_id": run_id, "thread_id": thread_id}),
    }

    # --- Create a job for provenance ------------------------------------------
    job_id: str | None = None
    try:
        job_id = await job_service.create_job(
            enterprise_id=enterprise.enterprise_id,
            job_type=data.assistant_id,
            thread_id=thread_id,
        )
    except Exception as e:
        logger.warning("Failed to create job: %s", e)

    # --- Checkout workspace (isolated temp dir) ------------------------------
    temp_workspace = await workspace_service.checkout(
        enterprise_id=enterprise.enterprise_id,
        thread_id=thread_id,
    )

    # --- Stream from agent ---------------------------------------------------
    agent_service = get_agent_service()
    command = None
    input_data = data.input
    if data.command and data.command.get("resume") is not None:
        command = data.command
        input_data = None

    last_state: dict | None = None

    try:
        async for state in agent_service.stream(
            graph_name=data.assistant_id,
            thread_id=thread_id,
            input_data=input_data,
            enterprise_id=enterprise.enterprise_id,
            job_id=job_id,
            command=command,
            workspace_root=temp_workspace,
        ):
            last_state = state
            messages = _serialize_messages(state.get("messages", []))
            yield {
                "event": "values",
                "data": json.dumps({"messages": messages}),
            }

        # --- Sync thread state back to DB ------------------------------------
        if last_state:
            await thread_service.update_values(
                thread_id,
                {"messages": _serialize_messages(last_state.get("messages", []))},
            )

        _runs[run_id]["status"] = "success"
        _runs[run_id]["updated_at"] = datetime.now(timezone.utc)

        # --- Commit workspace to S3 ------------------------------------------
        await workspace_service.commit(
            enterprise_id=enterprise.enterprise_id,
            thread_id=thread_id,
            temp_dir=temp_workspace,
        )

        if job_id:
            await job_service.update_status(job_id, "completed")

    except Exception as e:
        logger.exception("Agent execution failed for run %s", run_id)
        _runs[run_id]["status"] = "error"
        _runs[run_id]["updated_at"] = datetime.now(timezone.utc)
        if job_id:
            await job_service.update_status(job_id, "failed")
        yield {
            "event": "error",
            "data": json.dumps({"error": type(e).__name__, "message": str(e)}),
        }

    finally:
        # --- Always clean up temp workspace ----------------------------------
        await workspace_service.cleanup(temp_workspace)

    # --- End event -----------------------------------------------------------
    yield {"event": "end", "data": "null"}


async def get_run(
    thread_id: str, run_id: str, enterprise: EnterpriseContext
) -> RunResponse:
    """Fetch a single run record by id.

    Args:
        thread_id: Must match the run's thread (ownership check).
        run_id: The run to look up.
        enterprise: Authenticated tenant context.

    Returns:
        ``RunResponse`` for the requested run.

    Raises:
        HTTPException 404: If run not found or belongs to a different thread.
    """
    await _assert_ownership(thread_id, enterprise)
    r = _runs.get(run_id)
    if not r or r["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return _to_response(r)


async def cancel_run(
    thread_id: str, run_id: str, enterprise: EnterpriseContext
) -> RunResponse:
    """Mark a run as interrupted (best-effort cancellation).

    Args:
        thread_id: Must match the run's thread.
        run_id: The run to cancel.
        enterprise: Authenticated tenant context.

    Returns:
        Updated ``RunResponse`` with ``status="interrupted"``.

    Raises:
        HTTPException 404: If run not found or belongs to a different thread.
    """
    await _assert_ownership(thread_id, enterprise)
    r = _runs.get(run_id)
    if not r or r["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")
    r["status"] = "interrupted"
    r["updated_at"] = datetime.now(timezone.utc)
    return _to_response(r)
