"""Web search tool — thin wrapper around Tavily search with provenance tracking.

Delegates the actual search to ``tavily-python``'s ``AsyncTavilyClient`` and
calls ``research_service.record_query`` to persist provenance.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from backend.services import research_service

logger = logging.getLogger(__name__)


@tool
async def web_search(
    query: str,
    num_results: int = 5,
    *,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Search the web for information using Tavily.

    Creates an ``AsyncTavilyClient``, runs the search, normalises results
    into a uniform format, and records the query in the ``research_queries``
    table for provenance tracking.

    Args:
        query: The search query string.
        num_results: Maximum number of results to return (default 5).

    Returns:
        dict with keys:
        - ``query_id`` (str | None): UUID of the recorded query, or ``None``
          if recording failed or no ``research_job_id`` was in config.
        - ``results`` (list[dict]): Each entry has ``url``, ``title``, ``snippet``.
        - ``error`` (str): Present only on failure, describes what went wrong.
    """
    # Read the job_id from LangGraph's per-run configurable
    research_job_id: str | None = config.get("configurable", {}).get("research_job_id")

    # --- Call Tavily search API ----------------------------------------------
    try:
        from tavily import AsyncTavilyClient

        client = AsyncTavilyClient()
        response = await client.search(query, max_results=num_results)
        raw_results = response.get("results", [])
    except Exception as e:
        logger.warning("web_search failed for query=%r: %s", query, e)
        return {"query_id": None, "error": str(e), "results": []}

    # --- Normalise Tavily response into uniform format -----------------------
    # Tavily returns: {"title", "url", "content" (snippet), "score", ...}
    results = [
        {
            "url": r.get("url", ""),
            "title": r.get("title", ""),
            "snippet": r.get("content", ""),
        }
        for r in raw_results
        if r.get("url")
    ]

    # --- Record the query in DB for provenance tracking ----------------------
    query_id: str | None = None
    if research_job_id:
        query_id = await research_service.record_query(
            research_job_id=research_job_id,
            query_text=query,
            results_count=len(results),
        )

    return {"query_id": query_id, "results": results}
