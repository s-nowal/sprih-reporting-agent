"""Run handler with SSE streaming stub."""

import json
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from backend.handlers.thread_handler import _assert_ownership, _threads
from backend.schemas.runs import RunCreate, RunResponse
from backend.security.auth import EnterpriseContext

# In-memory store — replaced by RunService + DB later
_runs: dict[str, dict] = {}


def _to_response(r: dict) -> RunResponse:
    return RunResponse(**r)


async def create_run(
    thread_id: str, data: RunCreate, enterprise: EnterpriseContext
) -> RunResponse:
    _assert_ownership(thread_id, enterprise)
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
    thread_id: str, data: RunCreate, enterprise: EnterpriseContext
) -> AsyncGenerator[dict, None]:
    """Yield SSE events. Stub returns a canned AI response.

    Production flow:
      1. ThreadService.get(thread_id) — verify + load state
      2. RunService.create(...) — persist run record
      3. AgentService.stream(...) — invoke langgraph graph.astream()
      4. yield SSE events from agent execution
    """
    t = _assert_ownership(thread_id, enterprise)
    run_id = str(uuid4())
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

    # Event 1: metadata
    yield {"event": "metadata", "data": json.dumps({"run_id": run_id})}

    # Determine response text
    if data.command and data.command.get("resume") is not None:
        content = "Acknowledged. Resuming from where we left off. (stub)"
    else:
        user_msg = ""
        if data.input and "messages" in data.input:
            msgs = data.input["messages"]
            if msgs:
                last = msgs[-1]
                user_msg = last.get("content", "") if isinstance(last, dict) else ""
        content = (
            f'Received: "{user_msg}". '
            "This is a stub response — agent execution is not wired yet."
        )

    # Append to thread state
    messages = t["values"].get("messages", [])
    if data.input and "messages" in data.input:
        messages.extend(data.input["messages"])
    ai_message = {
        "type": "ai",
        "id": str(uuid4()),
        "content": content,
    }
    messages.append(ai_message)
    t["values"]["messages"] = messages
    t["updated_at"] = now

    # Event 2: values (full state after step)
    yield {
        "event": "values",
        "data": json.dumps({"messages": messages}),
    }

    # Event 3: end
    _runs[run_id]["status"] = "success"
    _runs[run_id]["updated_at"] = datetime.now(timezone.utc)
    yield {"event": "end", "data": "null"}


async def get_run(
    thread_id: str, run_id: str, enterprise: EnterpriseContext
) -> RunResponse:
    _assert_ownership(thread_id, enterprise)
    r = _runs.get(run_id)
    if not r or r["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return _to_response(r)


async def cancel_run(
    thread_id: str, run_id: str, enterprise: EnterpriseContext
) -> RunResponse:
    _assert_ownership(thread_id, enterprise)
    r = _runs.get(run_id)
    if not r or r["thread_id"] != thread_id:
        raise HTTPException(status_code=404, detail="Run not found")
    r["status"] = "interrupted"
    r["updated_at"] = datetime.now(timezone.utc)
    return _to_response(r)
