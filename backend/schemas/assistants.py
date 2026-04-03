"""Assistant request/response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AssistantResponse(BaseModel):
    assistant_id: str
    graph_id: str
    name: str
    config: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    version: int = 1


class AssistantSearch(BaseModel):
    graph_id: str | None = None
    metadata: dict[str, Any] | None = None
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)
