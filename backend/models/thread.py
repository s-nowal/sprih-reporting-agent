"""Thread model — persists Agent Protocol thread state to MariaDB."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Thread(Base):
    """ORM model for a conversation thread.

    Threads are the unit of continuity in the Agent Protocol — each run
    belongs to a thread and the thread accumulates state across runs.

    The ``mirror_*`` columns hold the per-thread mapping to a file mirror
    backend (Google Drive today, SharePoint potentially). They are
    populated lazily by ``mirror.MirrorProvider.setup_thread_folder`` on
    the first run that has a connected mirror; on subsequent runs the
    same row drives sync_in / sync_out. Storing them on the thread row
    rather than a side table keeps the relationship explicit (one folder
    per thread) and avoids an extra join on the hot path.

    Attributes:
        thread_id: UUID primary key.
        enterprise_id: Tenant that owns this thread.
        status: Lifecycle state (``"idle"``, ``"busy"``, ``"interrupted"``, ``"error"``).
        metadata_: Arbitrary JSON metadata set by the client.
        values: JSON dict of accumulated thread state values.
        interrupts: JSON dict of pending interrupts.
        mirror_provider: Provider key (``"google_drive"``) for the mirror
            folder backing this thread, or ``None`` if no mirror is connected.
        mirror_folder_id: Provider-side folder id for the per-thread folder.
        mirror_thread_title: Human-readable folder name (e.g. ``"plum-beacon-810"``)
            used as the per-thread folder name in the mirror.
        mirror_last_synced_at: Timestamp of the most recent successful
            bidirectional sync. Files modified after this on either side
            are eligible to transfer on the next turn.
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

    mirror_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    mirror_folder_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    mirror_thread_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    mirror_last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (Index("ix_threads_enterprise_id", "enterprise_id"),)
