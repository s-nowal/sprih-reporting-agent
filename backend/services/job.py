"""Job lifecycle service — CRUD for the ``jobs`` table.

Jobs are cross-cutting: any flow (agent runs, cron refresh, ERP auto-load,
internal research) creates a job to track its async execution. This service
has no dependency on the agent layer.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from backend.infra.registry import get_db
from backend.models.job import Job

logger = logging.getLogger(__name__)


async def create_job(
    enterprise_id: str,
    job_type: str,
    thread_id: str | None = None,
    config: dict[str, Any] | None = None,
) -> str:
    """Insert a new row in the ``jobs`` table.

    Args:
        enterprise_id: The tenant that owns this job (from JWT).
        job_type: Job category (``"research"``, ``"extraction"``, etc.).
        thread_id: The conversation thread that triggered the job.
        config: Optional JSON-serialisable config dict stored on the row.

    Returns:
        The UUID string of the newly created job.

    Raises:
        SQLAlchemy errors propagate — caller should handle them.
    """
    job_id = str(uuid4())
    db = get_db()
    async with db() as session:
        session.add(
            Job(
                id=job_id,
                enterprise_id=enterprise_id,
                thread_id=thread_id,
                job_type=job_type,
                status="running",
                config=config,
            )
        )
        await session.commit()
    return job_id


async def update_status(job_id: str, status: str) -> None:
    """Update the ``status`` column of an existing job row.

    Args:
        job_id: UUID of the job to update.
        status: New status string (``"completed"``, ``"failed"``, etc.).

    Returns:
        None. Silently does nothing if the job_id doesn't exist.
    """
    db = get_db()
    async with db() as session:
        stmt = select(Job).where(Job.id == job_id)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.status = status
            await session.commit()
