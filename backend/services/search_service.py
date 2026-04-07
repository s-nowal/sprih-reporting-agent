"""Search service — persists search query provenance to the DB.

Owns the two search provenance tables:
- ``search_queries``: one row per query issued to a search API.
- ``search_results``: one row per organic result returned by that query.

The result UUIDs (``result_id``) are handed to agents so they can call
``web_fetch`` without ever handling raw URLs directly.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from backend.infra.registry import get_session_factory
from backend.models.search_query import SearchQuery
from backend.models.search_result import SearchResult

logger = logging.getLogger(__name__)


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
                        query_id=query_id,
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
