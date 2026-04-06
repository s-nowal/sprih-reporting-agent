"""DataSource model — tracks every fetched URL or uploaded file.

No entity_id or s3_silver_path — those are extraction concerns.
Backlinks from extraction records point here via source_id.

When a URL is fetched for the first time ``origin_source_id`` is NULL — that
row is the canonical source. On subsequent fetches of the same URL across
different jobs, a new row is created with ``origin_source_id`` pointing to
the canonical row so downstream agents can reuse existing extraction results.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(36))
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jobs.id"), nullable=True
    )
    search_result_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("search_results.id"), nullable=True
    )
    # NULL on the canonical row; set on cross-job dedup rows.
    origin_source_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("data_sources.id"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(30))  # web_page, web_pdf, etc.
    source_ref: Mapped[str] = mapped_column(String(2048))  # URL or filename
    s3_bronze_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="fetched")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_data_sources_enterprise_id", "enterprise_id"),
        Index("ix_data_sources_enterprise_source_ref", "enterprise_id", "source_ref"),
    )
