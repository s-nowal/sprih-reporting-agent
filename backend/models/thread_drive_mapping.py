"""ThreadDriveMapping model — links a thread to its Drive folder + sync state.

One row per ``(enterprise_id, thread_id)``. Holds the Drive folder ID
provisioned for the thread, the human-readable thread title used as the
folder name, and the timestamp of the last successful sync — used by the
Drive sync service to decide which files to pull/push on each turn.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ThreadDriveMapping(Base):
    """ORM model for the Drive folder backing a thread.

    Attributes:
        thread_id: Conversation thread id (PK).
        enterprise_id: Tenant that owns this mapping.
        agent_name: The graph name (``"reporting-agent"`` etc.) — determines
            which agent-name subfolder under the parent the thread folder
            lives in (``Sprih/{agent_name}/{thread_title}``).
        thread_title: Human-readable folder name. Generated at mapping creation
            time and stable thereafter unless explicitly renamed.
        drive_folder_id: Drive ID of the per-thread folder.
        last_synced_at: Timestamp of the most recent successful bidirectional
            sync. Files modified in Drive after this time are pulled in;
            S3 files newer than this are pushed out.
        created_at: Row creation timestamp.
    """

    __tablename__ = "thread_drive_mappings"

    thread_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    enterprise_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("enterprises.enterprise_id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_name: Mapped[str] = mapped_column(String(64), nullable=False)
    thread_title: Mapped[str] = mapped_column(String(200), nullable=False)
    drive_folder_id: Mapped[str] = mapped_column(String(128), nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
