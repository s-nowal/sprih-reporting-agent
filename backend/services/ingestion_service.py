"""Ingestion service — persists crawled/searched content to bronze storage and DB.

Owns the full provenance pipeline that any search or crawl tool uses:
- ``record_query``: log a search query in ``research_queries``
- ``store_page``: save web page markdown to bronze + create ``data_sources`` row
- ``store_binary``: save binary file (PDF, XLSX, …) to bronze + create ``data_sources`` row
- ``check_duplicate``: skip re-fetching the same URL within a job

This service is agent-agnostic — the Research Agent, Reporting Agent, or any
future agent's tools can call it.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from backend.infra.registry import get_session_factory, get_storage
from backend.models.data_source import DataSource
from backend.models.research_query import ResearchQuery

logger = logging.getLogger(__name__)

PREVIEW_LENGTH = 500


async def record_search_query(
    research_job_id: str,
    search_query_text: str,
    results_count: int,
) -> str:
    """Insert a row in ``research_queries`` for provenance tracking.

    Called by any search tool after a web search to record which query was
    run and how many results it returned.

    Args:
        research_job_id: FK to the parent job in the ``jobs`` table.
        query_text: The exact search query string sent to the search API.
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
                    query_text=search_query_text,
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
    """Check if a URL has already been crawled within the same job.

    Queries ``data_sources`` by ``(source_ref, research_job_id)``.

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


async def store_page(
    enterprise_id: str,
    research_job_id: str | None,
    research_query_id: str | None,
    url: str,
    markdown_content: str,
) -> dict[str, Any]:
    """Save a crawled web page to bronze storage and record it in the DB.

    Writes ``content.md`` and ``meta.json`` to the bronze directory, then
    creates a ``data_sources`` row linking the file to its provenance chain.

    Args:
        enterprise_id: Tenant that owns this source (from JWT).
        research_job_id: FK to the parent job (WHY this was fetched).
        research_query_id: FK to the query that discovered this URL
            (``None`` if crawled directly without a search step).
        url: The original page URL (stored as ``source_ref``).
        markdown_content: The page content already converted to markdown.

    Returns:
        dict with ``source_id``, ``s3_bronze_path``, ``source_type``, ``preview``.
    """
    source_id = str(uuid4())
    now = datetime.now(timezone.utc)
    storage = get_storage()

    # --- Write content + metadata sidecar to bronze --------------------------
    bronze_dir = f"enterprise/{enterprise_id}/bronze/{source_id}"
    storage.write_text(f"{bronze_dir}/content.md", markdown_content)

    meta = {
        "source_ref": url,
        "source_type": "web_page",
        "content_length": len(markdown_content),
        "crawled_at": now.isoformat(),
    }
    storage.write_text(f"{bronze_dir}/meta.json", json.dumps(meta, indent=2))

    # --- Create data_sources row ---------------------------------------------
    s3_bronze_path = f"{bronze_dir}/"
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            session.add(
                DataSource(
                    id=source_id,
                    enterprise_id=enterprise_id,
                    research_job_id=research_job_id,
                    research_query_id=research_query_id,
                    source_type="web_page",
                    source_ref=url,
                    s3_bronze_path=s3_bronze_path,
                    status="fetched",
                    fetched_at=now,
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning("Failed to persist data_source for %s: %s", url, e)

    preview = markdown_content[:PREVIEW_LENGTH].strip()
    return {
        "source_id": source_id,
        "s3_bronze_path": s3_bronze_path,
        "source_type": "web_page",
        "preview": preview,
    }


async def store_binary(
    enterprise_id: str,
    research_job_id: str | None,
    research_query_id: str | None,
    url: str,
    raw_bytes: bytes,
    content_type: str,
    http_status: int,
) -> dict[str, Any]:
    """Save a downloaded binary file to bronze storage and record it in the DB.

    Writes the original file and ``meta.json`` to the bronze directory, then
    creates a ``data_sources`` row. Binary conversion (PDF → text, etc.) is
    handled separately by the Extraction Agent.

    Args:
        enterprise_id: Tenant that owns this source (from JWT).
        research_job_id: FK to the parent job (WHY this was fetched).
        research_query_id: FK to the query that discovered this URL.
        url: The original download URL (stored as ``source_ref``).
        raw_bytes: The raw binary content.
        content_type: HTTP Content-Type header value.
        http_status: HTTP status code from the download.

    Returns:
        dict with ``source_id``, ``s3_bronze_path``, ``source_type``, ``preview``.
    """
    source_id = str(uuid4())
    now = datetime.now(timezone.utc)
    storage = get_storage()

    # --- Determine file extension and source type ----------------------------
    ext = url.rsplit(".", 1)[-1].lower() if "." in url else "bin"
    source_type = f"web_{ext}"  # web_pdf, web_xlsx, etc.

    # --- Write binary + metadata sidecar to bronze ---------------------------
    bronze_dir = f"enterprise/{enterprise_id}/bronze/{source_id}"
    storage.write(f"{bronze_dir}/original.{ext}", raw_bytes)

    meta = {
        "source_ref": url,
        "source_type": source_type,
        "http_status": http_status,
        "content_type": content_type,
        "content_length": len(raw_bytes),
        "crawled_at": now.isoformat(),
    }
    storage.write_text(f"{bronze_dir}/meta.json", json.dumps(meta, indent=2))

    # --- Create data_sources row ---------------------------------------------
    s3_bronze_path = f"{bronze_dir}/"
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
                    source_ref=url,
                    s3_bronze_path=s3_bronze_path,
                    status="fetched",
                    fetched_at=now,
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning("Failed to persist data_source for %s: %s", url, e)

    preview = f"({ext.upper()} downloaded, {len(raw_bytes)} bytes — pending extraction)"
    return {
        "source_id": source_id,
        "s3_bronze_path": s3_bronze_path,
        "source_type": source_type,
        "preview": preview,
    }
