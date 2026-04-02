"""Run request/response models (Agent Protocol compatible)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class RunCreate(BaseModel):
    assistant_id: str = "reporting-agent"
    input: dict[str, Any] | None = None
    command: dict[str, Any] | None = None
    config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    stream_mode: str | list[str] = "values"
    interrupt_before: list[str] | None = None
    interrupt_after: list[str] | None = None
    on_disconnect: Literal["cancel", "continue"] | None = None
    webhook: str | None = None


class RunResponse(BaseModel):
    run_id: str
    thread_id: str
    assistant_id: str
    created_at: datetime
    updated_at: datetime
    status: Literal[
        "pending", "running", "error", "success", "timeout", "interrupted"
    ] = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)
