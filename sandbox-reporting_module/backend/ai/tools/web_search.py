"""Web search tool — thin wrapper around Serper search with provenance tracking.

Posts to the Serper Google Search JSON API (``https://google.serper.dev/search``)
via ``httpx`` and calls ``search_service.record_search_query`` to persist
provenance. Reads ``SERPER_API_KEY`` from the environment.
"""

from __future__ import annotations
import logging
import os
from typing import Any
import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from backend.services import search_service

logger = logging.getLogger(__name__)
_SERPER_URL = "https://google.serper.dev/search"

@tool
async def web_search(
    search_query_text: str,
    num_results: int = 5,
    *,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Search Google for up-to-date information on any topic.

    Use this when you need current facts, recent events, statistics, or
    information that may not be in your training data. Input should be a
    specific, concise search query — not a question or full sentence.

    Args:
        search_query_text: The search query string (e.g. "EU CSRD reporting
            requirements 2024", not "What are the EU CSRD requirements?").
        num_results: Maximum number of results to return (default 5).

    Returns:
        dict with keys:
        - ``search_query_id`` (str | None): UUID of the recorded query, or
          ``None`` if no ``job_id`` was in config.
        - ``results`` (list[dict]): Google organic results. Each entry has
          ``result_id``, ``url``, ``title``, ``snippet``, and ``position``.
          Pass ``result_id`` to ``web_fetch`` to download that page.
        - ``error`` (str): Present only on failure, describes what went wrong.

    Raises:
        Nothing — all exceptions are caught and returned as ``error`` keys.
    """
    # Read the job_id from LangGraph's per-run configurable
    job_id: str | None = config.get("configurable", {}).get("job_id")

    # --- Call Serper search API ----------------------------------------------
    try:
        api_key = os.environ["SERPER_API_KEY"]
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                _SERPER_URL,
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": search_query_text, "num": num_results},
            )
            response.raise_for_status()
            raw_results = response.json().get("organic", [])
    except Exception as e:
        logger.warning("web_search failed for query=%r: %s", search_query_text, e)
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

    # --- Persist query + results, get back result_ids for the agent ----------
    search_query_id: str | None = None
    if job_id:
        search_query_id, results = await search_service.record_search_query(
            job_id=job_id,
            search_query_text=search_query_text,
            results=results,
        )

    return {"search_query_id": search_query_id, "results": results}
