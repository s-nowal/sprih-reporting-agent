"""CRUD helpers for ``mirror_credentials`` rows.

Pure DB layer — no provider-specific logic. Provider implementations and
the OAuth router both call into here so credential storage stays
centralised.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, select, update

from backend.infra.registry import get_db
from backend.models.mirror_credentials import MirrorCredentials

logger = logging.getLogger(__name__)


async def load(enterprise_id: str, provider: str) -> MirrorCredentials | None:
    """Fetch credentials for one (enterprise, provider) pair.

    Args:
        enterprise_id: Tenant id.
        provider: Provider key (``"google_drive"`` etc.).

    Returns:
        The ORM row or ``None`` if the enterprise has not connected this
        provider.
    """
    db = get_db()
    async with db() as session:
        return await session.get(MirrorCredentials, (enterprise_id, provider))


async def load_first(enterprise_id: str) -> MirrorCredentials | None:
    """Return any credentials row for an enterprise, or ``None``.

    Used by ``mirror.get_provider`` to pick the active provider when an
    enterprise has connected exactly one (the current expectation). When
    multi-provider mirroring becomes a thing this should grow a policy.

    Args:
        enterprise_id: Tenant id.

    Returns:
        The first ``MirrorCredentials`` row for the enterprise, or ``None``.
    """
    db = get_db()
    async with db() as session:
        stmt = (
            select(MirrorCredentials)
            .where(MirrorCredentials.enterprise_id == enterprise_id)
            .limit(1)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def store(
    enterprise_id: str,
    provider: str,
    refresh_token: str,
    agent_email: str,
    scopes: list[str],
    parent_folder_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> None:
    """Insert or update credentials for one (enterprise, provider) pair.

    On update, ``parent_folder_id`` and ``config`` are only overwritten
    when explicitly passed (so rotating a refresh token doesn't clobber
    a previously-set parent folder).

    Args:
        enterprise_id: Tenant id.
        provider: Provider key.
        refresh_token: OAuth refresh token.
        agent_email: Email of the account that authorised the app.
        scopes: List of OAuth scopes the token was issued with.
        parent_folder_id: Provider-side id of the shared root folder.
            Pass ``None`` to leave any existing value untouched.
        config: Provider-specific extra fields. Pass ``None`` to leave
            any existing value untouched.
    """
    db = get_db()
    async with db() as session:
        existing = await session.get(MirrorCredentials, (enterprise_id, provider))
        if existing is None:
            row = MirrorCredentials(
                enterprise_id=enterprise_id,
                provider=provider,
                agent_email=agent_email,
                refresh_token=refresh_token,
                scopes=" ".join(scopes),
                parent_folder_id=parent_folder_id,
                config=config,
            )
            session.add(row)
        else:
            existing.refresh_token = refresh_token
            existing.agent_email = agent_email
            existing.scopes = " ".join(scopes)
            if parent_folder_id is not None:
                existing.parent_folder_id = parent_folder_id
            if config is not None:
                existing.config = config
        await session.commit()


async def set_parent_folder(
    enterprise_id: str, provider: str, parent_folder_id: str
) -> bool:
    """Update only the ``parent_folder_id`` for one (enterprise, provider).

    Uses an explicit UPDATE statement (not ORM fetch-then-modify) so the
    write always reaches the DB regardless of SQLAlchemy's dirty-tracking.

    Args:
        enterprise_id: Tenant id.
        provider: Provider key.
        parent_folder_id: New parent folder id to overwrite whatever is stored.

    Returns:
        ``True`` if a row was updated, ``False`` if no credentials exist
        for that (enterprise, provider).
    """
    db = get_db()
    async with db() as session:
        result = await session.execute(
            update(MirrorCredentials)
            .where(
                MirrorCredentials.enterprise_id == enterprise_id,
                MirrorCredentials.provider == provider,
            )
            .values(parent_folder_id=parent_folder_id)
        )
        await session.commit()
        return result.rowcount > 0


async def clear(enterprise_id: str, provider: str) -> None:
    """Delete all credentials for one (enterprise, provider).

    Called when the OAuth flow is restarted so any stale token and folder
    mapping are removed before the fresh grant is persisted by the callback.

    Args:
        enterprise_id: Tenant id.
        provider: Provider key (``"google_drive"`` etc.).
    """
    db = get_db()
    async with db() as session:
        await session.execute(
            delete(MirrorCredentials).where(
                MirrorCredentials.enterprise_id == enterprise_id,
                MirrorCredentials.provider == provider,
            )
        )
        await session.commit()


async def get_status(enterprise_id: str) -> dict[str, Any]:
    """Return a summary of every provider this enterprise has connected.

    Used by the dev-time status endpoint and any future admin UI.

    Args:
        enterprise_id: Tenant id.

    Returns:
        Dict shaped as ``{"connected": bool, "providers": [<per-provider dict>]}``
        where each per-provider dict has ``provider``, ``agent_email``, and
        ``parent_folder_id``.
    """
    db = get_db()
    async with db() as session:
        stmt = select(MirrorCredentials).where(
            MirrorCredentials.enterprise_id == enterprise_id
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return {
        "connected": bool(rows),
        "providers": [
            {
                "provider": r.provider,
                "agent_email": r.agent_email,
                "parent_folder_id": r.parent_folder_id,
            }
            for r in rows
        ],
    }
