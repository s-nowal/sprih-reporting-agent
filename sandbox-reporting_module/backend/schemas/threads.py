"""Thread request/response models (Agent Protocol compatible)."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ThreadCreate(BaseModel):
    thread_id: str | None = None
    metadata: dict[str, Any] | None = None
    if_exists: Literal["raise", "do_nothing"] | None = None


class ThreadUpdate(BaseModel):
    metadata: dict[str, Any]


class ThreadSearch(BaseModel):
    metadata: dict[str, Any] | None = None
    status: Literal["idle", "busy", "interrupted", "error"] | None = None
    limit: int = Field(default=10, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ThreadResponse(BaseModel):
    thread_id: str
    created_at: datetime
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: Literal["idle", "busy", "interrupted", "error"] = "idle"
    values: dict[str, Any] = Field(default_factory=dict)
    interrupts: dict[str, list[Any]] = Field(default_factory=dict)
