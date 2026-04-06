"""Ingestion service — persists crawled/searched content to bronze storage and DB.

Owns the full provenance pipeline that any search or crawl tool uses:
- ``record_query``: log a search query in ``search_queries``
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
from backend.models.search_query import SearchQuery
from backend.models.search_result import SearchResult

logger = logging.getLogger(__name__)

PREVIEW_LENGTH = 500


async def record_search_query(
    job_id: str,
    search_query_text: str,
    results: list[dict],
) -> tuple[str, list[dict]]:
    """Insert a ``search_queries`` row and one ``search_results`` row per organic result.

    Each result gets a UUID (``result_id``) that the agent passes to
    ``web_fetch`` instead of a raw URL, making fetches fully traceable.

    Args:
        job_id: FK to the parent job in the ``jobs`` table.
        search_query_text: The exact query string sent to the search API.
        results: Organic results from the search API. Each dict must have
            ``url``; ``title``, ``snippet``, and ``position`` are optional.

    Returns:
        A tuple of ``(query_id, enriched_results)`` where ``enriched_results``
        is a copy of ``results`` with a ``result_id`` field added to each entry.
        Returns the generated IDs even if the DB write fails.
    """
    query_id = str(uuid4())
    enriched = [
        {**r, "result_id": str(uuid4()), "position": r.get("position", i + 1)}
        for i, r in enumerate(results)
    ]
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            session.add(
                SearchQuery(
                    id=query_id,
                    job_id=job_id,
                    query_text=search_query_text,
                    results_count=len(enriched),
                    executed_at=datetime.now(timezone.utc),
                )
            )
            for r in enriched:
                session.add(
                    SearchResult(
                        id=r["result_id"],
                        search_result_id=search_result_id,
                        position=r["position"],
                        url=r["url"],
                        title=r.get("title"),
                        snippet=r.get("snippet"),
                    )
                )
            await session.commit()
    except Exception as e:
        logger.warning("Failed to persist search_query: %s", e)
    return query_id, enriched


async def get_search_result(result_id: str) -> dict | None:
    """Return the stored URL and metadata for a search result row.

    Used by ``web_fetch`` to resolve a ``result_id`` to its URL without
    the agent ever handling raw URLs directly.

    Args:
        result_id: UUID of the ``search_results`` row.

    Returns:
        Dict with ``url``, ``title``, ``snippet``, ``query_id``, or ``None``
        if the row doesn't exist or the DB lookup fails.
    """
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(SearchResult).where(SearchResult.id == result_id)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            return {
                "url": row.url,
                "title": row.title,
                "snippet": row.snippet,
                "query_id": row.query_id,
            }
    except Exception as e:
        logger.warning("Failed to fetch search result %s: %s", result_id, e)
        return None


async def check_duplicate(
    source_ref: str,
    job_id: str | None,
) -> dict[str, Any] | None:
    """Check if a URL has already been crawled within the same job.

    Queries ``data_sources`` by ``(source_ref, job_id)``.

    Args:
        source_ref: The URL to check.
        job_id: The job to scope the check to. If ``None``, always
            returns ``None`` (no dedup without a job context).

    Returns:
        A dict with ``source_id``, ``s3_bronze_path``, ``source_type``,
        ``preview``, and ``duplicate=True`` if a match is found.
        ``None`` if no duplicate exists or the check fails.
    """
    if not job_id:
        return None
    try:
        session_factory = get_session_factory()
        async with session_factory() as session:
            stmt = select(DataSource).where(
                DataSource.source_ref == source_ref,
                DataSource.job_id == job_id,
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
    job_id: str | None,
    search_result_id: str | None,
    url: str,
    markdown_content: str,
) -> dict[str, Any]:
    """Save a crawled web page to bronze storage and record it in the DB.

    Writes ``content.md`` and ``meta.json`` to the bronze directory, then
    creates a ``data_sources`` row linking the file to its provenance chain.

    Args:
        enterprise_id: Tenant that owns this source (from JWT).
        job_id: FK to the parent job (WHY this was fetched).
        search_result_id: FK to the ``search_results`` row that led to this fetch
            (``None`` if fetched outside of a search flow).
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
                    job_id=job_id,
                    search_result_id=search_result_id,
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
    job_id: str | None,
    search_result_id: str | None,
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
        job_id: FK to the parent job (WHY this was fetched).
        search_result_id: FK to the ``search_results`` row that led to this fetch.
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
                    job_id=job_id,
                    search_result_id=search_result_id,
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
