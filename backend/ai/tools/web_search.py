"""Web search tool — thin wrapper around Tavily search with provenance tracking.

Delegates the actual search to ``tavily-python``'s ``AsyncTavilyClient`` and
calls ``research_service.record_query`` to persist provenance.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from backend.services import ingestion_service

logger = logging.getLogger(__name__)


@tool
async def web_search(
    search_query_text: str,
    num_results: int = 5,
    *,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Search the web for information using Tavily.

    Creates an ``AsyncTavilyClient``, runs the search, normalises results
    into a uniform format, and records the query in the ``research_queries``
    table for provenance tracking.

    Args:
        search_query_text: The search query string.
        num_results: Maximum number of results to return (default 5).

    Returns:
        dict with keys:
        - ``search_query_id`` (str | None): UUID of the recorded query, or ``None``
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
        response = await client.search(search_query_text, max_results=num_results)
        raw_results = response.get("results", [])
    except Exception as e:
        logger.warning("web_search failed for query=%r: %s", search_query_text, e)
        return {"search_query_id": None, "error": str(e), "results": []}

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
    search_query_id: str | None = None
    if research_job_id:
        search_query_id = await ingestion_service.record_search_query(
            research_job_id=research_job_id,
            search_query_text=search_query_text,
            results_count=len(results),
        )

    return {"search_query_id": search_query_id, "results": results}
