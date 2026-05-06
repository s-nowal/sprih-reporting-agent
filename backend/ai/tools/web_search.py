"""Web search tool — thin ``@tool`` wrapper over ``services/ingestion/search.search_web``.

All Serper API logic and provenance DB writes live in
``backend.services.ingestion.search``. This module owns only the LangChain
``@tool`` wrapper that reads config and delegates.

``search_web`` is re-exported here so ``mcp/server.py`` imports remain unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from backend.services.ingestion.search import search_web  # noqa: F401 — re-exported for mcp/server.py

logger = logging.getLogger(__name__)


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
    """
    job_id: str | None = config.get("configurable", {}).get("job_id")
    return await search_web(
        query=search_query_text,
        num_results=num_results,
        job_id=job_id,
    )
