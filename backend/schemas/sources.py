"""Source document request/response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SourceUploadResponse(BaseModel):
    id: str
    enterprise_id: str
    source_type: str
    source_ref: str
    status: str = "fetched"
    created_at: datetime


class SourceResponse(BaseModel):
    id: str
    enterprise_id: str
    source_type: str
    source_ref: str
    s3_bronze_path: str | None = None
    status: str
    fetched_at: datetime | None = None
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)
