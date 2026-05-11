"""Thread persistence service — DB-backed CRUD for the ``threads`` table.

Threads map 1-to-1 with Agent Protocol conversation threads.  Each row holds
the thread's status, accumulated state values, and any pending interrupts so
that threads survive server restarts.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select

from backend.infra.registry import get_db
from backend.models.thread import Thread

logger = logging.getLogger(__name__)


async def create(thread_id: str, enterprise_id: str, metadata: dict[str, Any]) -> dict:
    """Insert a new thread row and return it as a plain dict.

    Args:
        thread_id: UUID string to use as the primary key.
        enterprise_id: Tenant that owns this thread.
        metadata: Arbitrary client-supplied JSON metadata.

    Returns:
        Dict representation of the new thread row.

    Raises:
        SQLAlchemy errors propagate — caller should handle conflicts.
    """
    db = get_db()
    async with db() as session:
        row = Thread(
            thread_id=thread_id,
            enterprise_id=enterprise_id,
            status="idle",
            metadata_=metadata,
            values={},
            interrupts={},
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return _to_dict(row)


async def get(thread_id: str) -> dict | None:
    """Fetch a thread row by primary key.

    Args:
        thread_id: UUID string of the thread to fetch.

    Returns:
        Dict representation of the row, or ``None`` if not found.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(Thread, thread_id)
        return _to_dict(row) if row else None


async def search(
    enterprise_id: str,
    metadata: dict | None,
    status: str | None,
    limit: int = 10,
    offset: int = 0,
) -> list[dict]:
    """Return threads belonging to an enterprise, optionally filtered.

    Args:
        enterprise_id: Tenant to filter by.
        metadata: Key/value pairs that must all be present in ``metadata_``.
            Filtered in Python after the DB query (JSON column portability).
        status: If set, only return threads with this status value.
        limit: Maximum number of results to return.
        offset: Number of rows to skip for pagination.

    Returns:
        List of thread dicts ordered by ``updated_at`` descending.
    """
    db = get_db()
    async with db() as session:
        stmt = (
            select(Thread)
            .where(Thread.enterprise_id == enterprise_id)
            .order_by(Thread.updated_at.desc())
        )
        if status:
            stmt = stmt.where(Thread.status == status)

        result = await session.execute(stmt)
        rows = result.scalars().all()

    # --- Filter by metadata key/value pairs in Python ---
    if metadata:
        rows = [
            r for r in rows
            if all((r.metadata_ or {}).get(k) == v for k, v in metadata.items())
        ]

    return [_to_dict(r) for r in rows[offset : offset + limit]]


async def update(thread_id: str, metadata: dict[str, Any]) -> dict | None:
    """Merge new metadata into an existing thread row.

    Args:
        thread_id: UUID of the thread to update.
        metadata: Key/value pairs to merge into the existing ``metadata_``.

    Returns:
        Updated dict representation of the row, or ``None`` if not found.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(Thread, thread_id)
        if row is None:
            return None
        existing = dict(row.metadata_ or {})
        existing.update(metadata)
        row.metadata_ = existing
        await session.commit()
        await session.refresh(row)
        return _to_dict(row)


async def set_status(thread_id: str, status: str) -> None:
    """Update the lifecycle ``status`` column on a thread row.

    Used by the run handler to flip a thread between ``idle`` / ``busy`` /
    ``error`` / ``interrupted`` around an agent run. Silent no-op if the
    thread doesn't exist (which can only happen if it was deleted mid-run).

    Args:
        thread_id: UUID of the thread to update.
        status: One of ``idle``, ``busy``, ``interrupted``, ``error``.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(Thread, thread_id)
        if row is None:
            return
        row.status = status
        await session.commit()


async def update_values(thread_id: str, values: dict[str, Any]) -> None:
    """Persist agent state values back to the thread row after a run completes.

    Args:
        thread_id: UUID of the thread to update.
        values: New state values dict to store (replaces the existing values).

    Returns:
        None. Silently does nothing if the thread_id doesn't exist.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(Thread, thread_id)
        if row is None:
            return
        row.values = values
        await session.commit()


async def delete(thread_id: str) -> bool:
    """Delete a thread row.

    Args:
        thread_id: UUID of the thread to delete.

    Returns:
        ``True`` if the row existed and was deleted, ``False`` otherwise.
    """
    db = get_db()
    async with db() as session:
        row = await session.get(Thread, thread_id)
        if row is None:
            return False
        await session.delete(row)
        await session.commit()
        return True


def _to_dict(row: Thread) -> dict:
    """Convert a Thread ORM row to the dict shape expected by the handler.

    Args:
        row: Thread ORM instance.

    Returns:
        Plain dict with keys matching ``ThreadResponse`` fields.
    """
    return {
        "thread_id": row.thread_id,
        "enterprise_id": row.enterprise_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "metadata": row.metadata_ or {},
        "status": row.status,
        "values": row.values or {},
        "interrupts": row.interrupts or {},
    }
