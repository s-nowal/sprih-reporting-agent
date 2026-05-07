"""MirrorCredentials model — OAuth + parent folder per (enterprise, provider).

Replaces the earlier ``google_credentials`` table with a provider-agnostic
shape so additional file-mirror backends (e.g. SharePoint via Microsoft
Graph) can plug in without a schema change.

One row per ``(enterprise_id, provider)`` pair. The ``config`` JSON column
holds provider-specific overflow that doesn't justify its own column —
e.g. ``tenant_id`` for SharePoint, ``site_id`` for SharePoint sites.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class MirrorCredentials(Base):
    """ORM model for an enterprise's connection to a single mirror provider.

    Attributes:
        enterprise_id: Tenant that owns these credentials. Composite PK
            with ``provider`` so an enterprise may (in the future) connect
            multiple providers concurrently.
        provider: Stable identifier of the mirror backend
            (``"google_drive"`` for now; ``"sharepoint"`` later).
        agent_email: The Google / Microsoft account the agent authenticates
            as. Stored for auditing — the refresh token is the secret.
        refresh_token: Long-lived OAuth refresh token. Used by the provider
            to mint short-lived access tokens on demand.
        scopes: Space-separated OAuth scopes the token was issued with.
        parent_folder_id: Provider-specific id of the shared root folder
            (e.g. the Drive folder named "Sprih" the user has shared with
            the agent). May be ``None`` until set via the auth router.
        config: Provider-specific extra fields stored as JSON. Keeps the
            schema stable as new providers add their own metadata.
        created_at: Row creation timestamp.
        updated_at: Last-write timestamp (refresh-token rotations etc.).
    """

    __tablename__ = "mirror_credentials"

    enterprise_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("enterprises.enterprise_id", ondelete="CASCADE"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    agent_email: Mapped[str] = mapped_column(String(320), nullable=False)
    refresh_token: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[str] = mapped_column(Text, nullable=False)
    parent_folder_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
