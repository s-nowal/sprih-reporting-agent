"""Research service — handles all DB operations for the research workflow.

Tools call this service to persist queries and sources.  This keeps DB logic
out of tool functions and in the service layer where it belongs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from backend.infra.registry import get_session_factory
from backend.models.data_source import DataSource
from backend.models.job import Job
from backend.models.research_query import ResearchQuery

logger = logging.getLogger(__name__)


async def create_research_job(
    enterprise_id: str,
    thread_id: str | None = None,
    config: dict | None = None,
) -> str:
    """Insert a new row in the ``jobs`` table with ``job_type='research'``.

    Args:
        enterprise_id: The tenant that owns this job (from JWT).
        thread_id: The conversation thread that triggered the research.
        config: Optional JSON-serialisable config dict stored on the job row.

    Returns:
        The UUID string of the newly created job.

    Raises:
        SQLAlchemy errors propagate — caller should handle them.
    """
    job_id = str(uuid4())
    session_factory = get_session_factory()
    async with session_factory() as session:
        session.add(
            Job(
                id=job_id,
                enterprise_id=enterprise_id,
                thread_id=thread_id,
                job_type="research",
                status="running",
                config=config,
            )
        )
        await session.commit()
    return job_id


async def update_job_status(job_id: str, status: str) -> None:
    """Update the ``status`` column of an existing job row.

    Args:
        job_id: UUID of the job to update.
        status: New status string (e.g. ``"completed"``, ``"failed"``).

    Returns:
        None. Silently does nothing if the job_id doesn't exist.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(Job).where(Job.id == job_id)
        result = await session.execute(stmt)
        job = result.scalar_one_or_none()
        if job:
            job.status = status
            await session.commit()


async def record_query(
    research_job_id: str,
    query_text: str,
    results_count: int,
) -> str:
    """Insert a row in ``research_queries`` for provenance tracking.

    Called by the ``web_search`` tool after each Tavily search to record
    which query was run and how many results it returned.

    Args:
        research_job_id: FK to the parent job in the ``jobs`` table.
        query_text: The exact search query string sent to Tavily.
        results_count: Number of URLs returned by the search.

    Returns:
        The UUID string of the newly created query row. Always returns a
        query_id even if the DB write fails (logged as warning).
    """
    query_id = str(uuid4())
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            session.add(
                ResearchQuery(
                    id=query_id,
                    research_job_id=research_job_id,
                    query_text=query_text,
                    results_count=results_count,
                    executed_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning("Failed to persist research_query: %s", e)
    return query_id


async def check_duplicate(
    source_ref: str,
    research_job_id: str | None,
) -> dict[str, Any] | None:
    """Check if a URL has already been crawled within the same research job.

    Queries ``data_sources`` by ``(source_ref, research_job_id)``.  Used by
    ``web_crawl`` to avoid re-fetching the same URL within a single run.

    Args:
        source_ref: The URL to check.
        research_job_id: The job to scope the check to. If ``None``, always
            returns ``None`` (no dedup without a job context).

    Returns:
        A dict with ``source_id``, ``s3_bronze_path``, ``source_type``,
        ``preview``, and ``duplicate=True`` if a match is found.
        ``None`` if no duplicate exists or the check fails.
    """
    if not research_job_id:
        return None
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(DataSource).where(
                DataSource.source_ref == source_ref,
                DataSource.research_job_id == research_job_id,
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {
                "source_id": row.id,
                "s3_bronze_path": row.s3_bronze_path,
                "source_type": row.source_type,
                "preview": "(already crawled)",
                "duplicate": True,
            }
    except Exception as e:
        logger.warning("Dedup check failed: %s", e)
        return None


async def record_source(
    enterprise_id: str,
    research_job_id: str | None,
    research_query_id: str | None,
    source_ref: str,
    source_type: str,
    s3_bronze_path: str,
) -> str:
    """Insert a row in ``data_sources`` for a newly fetched URL or file.

    Called by the ``web_crawl`` tool after content has been downloaded and
    saved to bronze storage.

    Args:
        enterprise_id: Tenant that owns this source (from JWT).
        research_job_id: FK to the parent job (WHY this was fetched).
        research_query_id: FK to the query that discovered this URL
            (``None`` if the agent crawled directly without a search step).
        source_ref: The URL or original filename.
        source_type: e.g. ``"web_page"``, ``"web_pdf"``, ``"upload_pdf"``.
        s3_bronze_path: Relative storage path to the bronze directory.

    Returns:
        The UUID string of the newly created data_source row. Always returns
        a source_id even if the DB write fails (logged as warning).
    """
    source_id = str(uuid4())
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            session.add(
                DataSource(
                    id=source_id,
                    enterprise_id=enterprise_id,
                    research_job_id=research_job_id,
                    research_query_id=research_query_id,
                    source_type=source_type,
                    source_ref=source_ref,
                    s3_bronze_path=s3_bronze_path,
                    status="fetched",
                    fetched_at=datetime.now(timezone.utc),
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning("Failed to persist data_source for %s: %s", source_ref, e)
    return source_id
