"""GoogleCredentials model — OAuth refresh token + parent folder per enterprise.

One row per enterprise. ``refresh_token`` is obtained via the OAuth flow at
``/auth/google/start`` → ``/auth/google/callback``. ``drive_parent_folder_id``
is the ID of the *enterprise-owned* "Sprih" folder that has been shared with
the agent's Google account (e.g. ``sachchit.vekaria@sprih.com``).

For the test setup we reverse roles: the user account ``write.to.sachchit@gmail.com``
creates and owns the Sprih folder and shares it with the agent identity. In
production each enterprise creates the folder in their own Drive and shares it
with the Sprih agent identity — same code path, different folder owner.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class GoogleCredentials(Base):
    """ORM model for an enterprise's Google Drive integration.

    Attributes:
        enterprise_id: Tenant that owns these credentials (PK + FK).
        agent_email: The Google account the agent signs in as. Stored for
            auditing — the refresh token is the source of truth.
        refresh_token: Long-lived OAuth refresh token. Used by the Drive
            client to obtain short-lived access tokens on demand.
        scopes: Space-separated OAuth scopes the token was granted with.
        drive_parent_folder_id: Drive folder ID of the shared "Sprih" folder
            inside which the agent creates per-thread subfolders.
        created_at: Row creation timestamp.
        updated_at: Last-write timestamp (refresh token rotations etc.).
    """

    __tablename__ = "google_credentials"

    enterprise_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("enterprises.enterprise_id", ondelete="CASCADE"),
        primary_key=True,
    )
    agent_email: Mapped[str] = mapped_column(String(320), nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    drive_parent_folder_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
