"""ThreadMirrorMapping — per-thread linkage to a mirror provider folder.

Replaces the ``mirror_*`` columns that previously lived on the ``threads``
row. Splitting the linkage into its own table keeps the threads table
focused on conversation state and lets us add link-only columns
(e.g. ``last_link_check_at``) without churning the threads schema.

One row per ``(thread_id)`` because a thread is bound to at most one
mirror folder. Provider is stored too so we can support multiple
provider backends (Google Drive today, SharePoint later) without a
schema change.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ThreadMirrorMapping(Base):
    """ORM model for a thread → mirror-folder link.

    Attributes:
        thread_id: PK + FK into ``threads.thread_id``. Cascade delete so
            cleaning up a thread also drops its link row.
        provider: Provider key (``"google_drive"`` etc.).
        folder_id: Provider-side folder id. Looked up at sync time;
            stable across rename/move on the provider side.
        thread_title: Cached display name of the folder. Optional —
            when missing the UI falls back to fetching the name from
            the provider by ``folder_id``.
        last_synced_at: Timestamp of the most recent successful
            bidirectional sync. Files modified after this on either
            side are eligible to transfer on the next turn.
        created_at: Row creation timestamp.
        updated_at: Last-write timestamp.
    """

    __tablename__ = "thread_mirror_mappings"

    thread_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threads.thread_id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    folder_id: Mapped[str] = mapped_column(String(256), nullable=False)
    thread_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
