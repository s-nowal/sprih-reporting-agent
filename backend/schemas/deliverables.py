"""Deliverable (reports, questionnaires, etc.) response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DeliverableResponse(BaseModel):
    id: str
    thread_id: str | None = None
    enterprise_id: str
    entity_id: str | None = None
    type: str  # report, questionnaire, ...
    format: str  # docx, xlsx, md, ...
    status: str  # draft, review, approved, published
    s3_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
