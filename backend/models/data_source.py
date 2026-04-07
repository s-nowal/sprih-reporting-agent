"""DataSource model — tracks every fetched URL or uploaded file.

Public/private split (mirrors S3 layout):
  - ``enterprise_id = NULL``: public web content fetched by the Research Agent.
    S3 path is ``public/bronze/{source_id}/``. Accessible to all enterprises.
  - ``enterprise_id = <eid>``: private enterprise content (uploads, ERP exports).
    S3 path is ``enterprise/{eid}/bronze/uploads/{id}/`` or similar.
    Accessible only to the owning enterprise.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # NULL for public web sources; set for private enterprise content.
    enterprise_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jobs.id"), nullable=True
    )
    search_result_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("search_results.id"), nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(30))  # web_page, web_pdf, etc.
    source_ref: Mapped[str] = mapped_column(String(2048))  # URL or filename
    s3_bronze_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="fetched")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("ix_data_sources_enterprise_id", "enterprise_id"),
        # Global dedup index on source_ref alone — used by check_duplicate for
        # public sources. source_ref is VARCHAR(2048); 200-char prefix keeps
        # the key within MariaDB's 3072-byte limit.
        Index(
            "ix_data_sources_source_ref",
            "source_ref",
            mysql_length={"source_ref": 200},
        ),
    )
