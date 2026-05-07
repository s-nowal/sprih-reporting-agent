"""Enterprise model — top-level tenant row.

Threads, jobs, and integration credentials all reference an enterprise by
``enterprise_id``. The dev-mode auth bypass uses ``settings.default_enterprise_id``
which is seeded into this table at startup so the default tenant always exists.
"""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class Enterprise(Base):
    """ORM model for a tenant.

    Attributes:
        enterprise_id: Stable string id used throughout the system as the tenant
            scope (matches ``enterprise_id`` on threads, jobs, etc.). Not a UUID
            so the dev tenant can have a readable id like ``"sprih"``.
        name: Human-readable display name.
        created_at: Row creation timestamp.
    """

    __tablename__ = "enterprises"

    enterprise_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
