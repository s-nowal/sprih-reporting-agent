"""DataSource model — tracks every fetched URL or uploaded file.

No entity_id or s3_silver_path — those are extraction concerns.
Backlinks from extraction records point here via source_id.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(36))
    research_job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jobs.id"), nullable=True
    )
    research_query_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("research_queries.id"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(30))  # web_page, web_pdf, etc.
    source_ref: Mapped[str] = mapped_column(String(2048))  # URL or filename
    s3_bronze_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="fetched")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (Index("ix_data_sources_enterprise_id", "enterprise_id"),)
