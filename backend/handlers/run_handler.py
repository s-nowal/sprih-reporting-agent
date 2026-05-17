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

from backend.handlers.thread_handler import _assert_ownership
from backend.schemas.runs import RunCreate, RunResponse
from backend.security.auth import EnterpriseContext
from backend.services import job as job_service
from backend.services import mirror
from backend.services.agent import get_agent_service
from backend.services.agent import thread as thread_service
from backend.services.agent import workspace as workspace_service
from backend.services.agent.title import generate_thread_title

logger = logging.getLogger(__name__)

# In-memory store — replaced by RunService + DB later
_runs: dict[str, dict] = {}


def _to_response(r: dict) -> RunResponse:
    """Convert an internal run dict to a Pydantic ``RunResponse``."""
    return RunResponse(**r)


def _first_user_message(input_data: dict | None) -> str | None:
    """Extract the user-message text from a run input payload.

    The Agent Protocol input shape is ``{"messages": [{type|role, content}, ...]}``.
    For a fresh thread, the client sends a single human message; this helper
    returns its textual content. Returns ``None`` for resume calls (no input)
    or when no human message can be located.

    Args:
        input_data: The ``data.input`` value from a ``RunCreate`` request,
            or ``None`` when resuming from an interrupt.

    Returns:
        The plain-text content of the human message, or ``None``.
    """
    if not input_data:
        return None
    messages = input_data.get("messages") or []
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        kind = msg.get("type") or msg.get("role")
        if kind in ("human", "user"):
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                return content
            # Some clients send content as a list of parts; concatenate text.
            if isinstance(content, list):
                parts = [
                    p.get("text", "") for p in content
                    if isinstance(p, dict) and p.get("type") == "text"
                ]
                joined = " ".join(t for t in parts if t).strip()
                if joined:
                    return joined
    return None


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
    thread_row = await _assert_ownership(thread_id, enterprise)
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

    # --- Flip thread status to 'busy' for the duration of the run -----------
    # Per ConOps §2.1 / §2.4: threads.status is the canonical "is this thread
    # free to run?" signal. Returns to 'idle' on success or 'error' on failure
    # in the try/except below.
    await thread_service.set_status(thread_id, "busy")

    # --- Detect first-message state for title generation --------------------
    # If metadata.title is unset, the title generator runs at stream end
    # against the user message in this run's input.
    needs_title = not (thread_row.get("metadata") or {}).get("title")

    # --- Pull user edits from the mirror before the run --------------------
    # Mirror linkage is opt-in per thread now (see PUT /threads/{tid}/mirror).
    # ``sync_in`` is a no-op when no mapping exists, so this stays cheap on
    # threads that never linked a Drive folder.
    mirror_provider = None
    try:
        mirror_provider = await mirror.get_provider(enterprise.enterprise_id)
        if mirror_provider is not None:
            await mirror_provider.sync_in(
                enterprise_id=enterprise.enterprise_id,
                thread_id=thread_id,
                agent_name=data.assistant_id,
            )
    except Exception as e:
        # Mirror issues should not break the agent run — log and continue.
        logger.warning("Mirror sync_in failed for thread %s: %s", thread_id, e)

    # --- Resolve persistent workspace prefix --------------------------------
    # The agent now writes directly to storage via S3Backend, so there is no
    # checkout/commit cycle. The prefix scopes every file op to this thread.
    workspace_prefix = workspace_service.workspace_prefix(
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

    client_type = (data.config or {}).get("client_type", "browser")

    last_state: dict | None = None

    try:
        async for state in agent_service.stream(
            graph_name=data.assistant_id,
            thread_id=thread_id,
            input_data=input_data,
            enterprise_id=enterprise.enterprise_id,
            job_id=job_id,
            command=command,
            workspace_prefix=workspace_prefix,
            client_type=client_type,
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

        # --- Push agent writes back to the mirror (no-op if not connected) --
        # The agent's writes already landed in storage live (no commit step
        # needed) so sync_out can run as soon as streaming completes.
        try:
            if mirror_provider is not None:
                await mirror_provider.sync_out(
                    enterprise_id=enterprise.enterprise_id,
                    thread_id=thread_id,
                    agent_name=data.assistant_id,
                )
        except Exception as e:
            logger.warning("Mirror sync_out failed for thread %s: %s", thread_id, e)

        if job_id:
            await job_service.update_status(job_id, "completed")

        # --- First-message side-effect: generate and persist the title ------
        # Per ConOps §2.1: the user's first message is used to generate the
        # thread title and persist it on threads.metadata['title'], visible
        # in the chat header and the conversation history.
        if needs_title:
            user_msg = _first_user_message(input_data)
            if user_msg:
                try:
                    title = await generate_thread_title(user_msg)
                    await thread_service.update(thread_id, {"title": title})
                except Exception as e:
                    logger.warning(
                        "Title generation/persist failed for %s: %s",
                        thread_id, e,
                    )

        # --- Flip thread status back to 'idle' on success -------------------
        await thread_service.set_status(thread_id, "idle")

    except Exception as e:
        logger.exception("Agent execution failed for run %s", run_id)
        _runs[run_id]["status"] = "error"
        _runs[run_id]["updated_at"] = datetime.now(timezone.utc)
        if job_id:
            await job_service.update_status(job_id, "failed")
        await thread_service.set_status(thread_id, "error")
        yield {
            "event": "error",
            "data": json.dumps({"error": type(e).__name__, "message": str(e)}),
        }

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
