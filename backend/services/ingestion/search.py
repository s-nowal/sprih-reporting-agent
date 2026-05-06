"""Search service — Serper API calls and search query provenance.

Owns both the Serper search call and the two provenance tables:
- ``search_queries``: one row per query issued to a search API.
- ``search_results``: one row per organic result returned by that query.

The result UUIDs (``result_id``) are handed to agents so they can call
``web_fetch`` without ever handling raw URLs directly.

Two surfaces:
- ``search_web(query, num_results, job_id)``: plain async function — callable
  from LangGraph, the MCP server, a script, anywhere.
- ``record_search_query`` / ``get_search_result``: provenance DB operations
  used internally by ``search_web`` and by ``crawl.fetch_url``.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import select

from backend.infra.registry import get_db
from backend.models.search_query import SearchQuery
from backend.models.search_result import SearchResult

logger = logging.getLogger(__name__)

_SERPER_URL = "https://google.serper.dev/search"


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
        db = get_db()
        async with db() as session:
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

    Used by ``crawl.fetch_url`` to resolve a ``result_id`` to its URL without
    the agent ever handling raw URLs directly.

    Args:
        result_id: UUID of the ``search_results`` row.

    Returns:
        Dict with ``url``, ``title``, ``snippet``, ``query_id``, or ``None``
        if the row doesn't exist or the DB lookup fails.
    """
    try:
        db = get_db()
        async with db() as session:
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


async def search_web(
    query: str,
    num_results: int = 5,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Search Google via Serper and persist the query + results as provenance.

    Args:
        query: The search query string (e.g. "EU CSRD reporting requirements
            2024"). Should be a concise search query, not a full-sentence
            question.
        num_results: Maximum number of organic results to return (default 5).
        job_id: FK to the parent job used when persisting the query. If
            ``None``, the Serper call still runs but no ``search_queries``
            row is written, and result rows get locally-generated UUIDs
            without being saved to the DB.

    Returns:
        dict with keys:
        - ``search_query_id`` (str | None): UUID of the recorded query, or
          ``None`` when ``job_id`` is ``None`` or the DB write failed.
        - ``results`` (list[dict]): Google organic results. Each entry has
          ``result_id``, ``url``, ``title``, ``snippet``, and ``position``.
          Pass ``result_id`` to ``web_fetch`` to download that page.
        - ``error`` (str): Present only on failure, describes what went wrong.

    Raises:
        Nothing — all exceptions are caught and returned as ``error`` keys.
    """
    # --- Call Serper search API ----------------------------------------------
    try:
        api_key = os.environ["SERPER_API_KEY"]
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                _SERPER_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": num_results},
            )
            response.raise_for_status()
            raw_results = response.json().get("organic", [])
    except Exception as e:
        logger.warning("search_web failed for query=%r: %s", query, e)
        return {"search_query_id": None, "error": str(e), "results": []}

    # --- Normalise organic results (Serper uses "link" for URL) --------------
    results = [
        {
            "url": r["link"],
            "title": r.get("title"),
            "snippet": r.get("snippet"),
            "position": r.get("position", i + 1),
        }
        for i, r in enumerate(raw_results)
        if r.get("link")
    ]

    # --- Persist query + results, get back result_ids ------------------------
    search_query_id: str | None = None
    if job_id:
        search_query_id, results = await record_search_query(
            job_id=job_id,
            search_query_text=query,
            results=results,
        )

    return {"search_query_id": search_query_id, "results": results}
