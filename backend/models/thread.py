"""Thread model — persists Agent Protocol thread state to MariaDB."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Thread(Base):
    """ORM model for a conversation thread.

    Threads are the unit of continuity in the Agent Protocol — each run
    belongs to a thread and the thread accumulates state across runs.

    Mirror linkage (folder id, sync timestamp) lives in the separate
    ``thread_mirror_links`` table — see
    ``backend/models/thread_mirror_link.py``. Keeping it off the thread
    row lets us evolve the link schema independently and keeps queries
    of "all threads for this enterprise" cheap.

    Attributes:
        thread_id: UUID primary key.
        enterprise_id: Tenant that owns this thread.
        status: Lifecycle state (``"idle"``, ``"busy"``, ``"interrupted"``, ``"error"``).
        metadata_: Arbitrary JSON metadata set by the client.
        values: JSON dict of accumulated thread state values.
        interrupts: JSON dict of pending interrupts.
        created_at: Row creation timestamp (set by DB).
        updated_at: Last-modified timestamp (set by DB, auto-updated on each write).
    """

    __tablename__ = "threads"

    thread_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(String(36), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="idle")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    values: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    interrupts: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_threads_enterprise_id", "enterprise_id"),)
