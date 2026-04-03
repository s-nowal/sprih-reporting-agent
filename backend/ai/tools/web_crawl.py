"""Web crawl tool — fetches a URL and delegates persistence to ingestion_service.

For web pages: uses Tavily Extract to get clean markdown content.
For PDFs / other binaries: uses httpx to download raw bytes (conversion
handled separately by the Extraction Agent / Parser Agent).

The tool itself only fetches — all storage writes and DB operations are
handled by ``ingestion_service``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from backend.services import ingestion_service

logger = logging.getLogger(__name__)


async def _extract_with_tavily(url: str) -> str | None:
    """Extract web page content as markdown using Tavily Extract API.

    Creates an ``AsyncTavilyClient``, calls ``extract()`` with
    ``format="markdown"``, and returns the first result's raw content.

    Args:
        url: The web page URL to extract content from.

    Returns:
        Markdown string of the page content, or ``None`` if extraction
        failed or returned no content.
    """
    try:
        from tavily import AsyncTavilyClient

        # Tavily accepts a list of URLs; we always extract one at a time.
        client = AsyncTavilyClient()
        response = await client.extract(urls=[url], format="markdown")

        # Response shape: {"results": [{"url": ..., "raw_content": ...}], ...}
        results = response.get("results", [])
        if results and results[0].get("raw_content"):
            return results[0]["raw_content"]
        return None
    except Exception as e:
        logger.warning("Tavily extract failed for %s: %s", url, e)
        return None


async def _download_binary(url: str) -> tuple[bytes, str, int] | None:
    """Download a binary file (PDF, XLSX, etc.) via httpx.

    Follows redirects and enforces a 30-second timeout.

    Args:
        url: The URL pointing to a downloadable binary file.

    Returns:
        A tuple of ``(raw_bytes, content_type, http_status)`` on success,
        or ``None`` if the request failed for any reason (timeout, DNS,
        HTTP error status, etc.).
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type", ""), resp.status_code
    except Exception as e:
        logger.warning("Binary download failed for %s: %s", url, e)
        return None


def _is_binary_url(url: str) -> bool:
    """Heuristic check: does the URL path end with a known binary extension?

    Args:
        url: The URL to inspect.

    Returns:
        ``True`` if the URL ends with .pdf, .xlsx, .xls, .csv, .docx, or .doc.
    """
    lower = url.lower()
    return any(lower.endswith(ext) for ext in (".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc"))


@tool
async def web_crawl(
    url: str,
    query_id: str | None = None,
    *,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Fetch a URL, save its content to bronze storage, and record it in the database.

    Routing logic:
    - Binary URLs (.pdf, .xlsx, …) → ``httpx`` download → raw bytes to bronze.
    - Web pages → Tavily Extract → markdown to bronze.

    The tool only fetches content — all storage writes and DB operations
    are delegated to ``ingestion_service``.

    Args:
        url: The URL to fetch.
        query_id: The ``query_id`` returned by ``web_search`` (optional).
            Passed through to ``data_sources.research_query_id`` for
            provenance tracking.

    Returns:
        dict with keys:
        - ``source_id`` (str): UUID of the created data_source, or ``None`` on failure.
        - ``s3_bronze_path`` (str): Storage path to the bronze directory.
        - ``source_type`` (str): e.g. ``"web_page"``, ``"web_pdf"``.
        - ``preview`` (str): First 500 chars of content, or a status message.
        - ``duplicate`` (bool): Present and ``True`` if URL was already crawled.
        - ``error`` (str): Present only on failure, describes what went wrong.
    """
    # --- Read per-request config from LangGraph configurable -----------------
    enterprise_id: str = config.get("configurable", {}).get(
        "enterprise_id", "dev-enterprise"
    )
    research_job_id: str | None = config.get("configurable", {}).get("research_job_id")

    # --- Deduplication: skip if same URL already crawled in this job ----------
    dup = await ingestion_service.check_duplicate(url, research_job_id)
    if dup:
        return dup

    # --- PATH A: Binary content (PDF, Excel, etc.) ---------------------------
    if _is_binary_url(url):
        result = await _download_binary(url)
        if result is None:
            return {"source_id": None, "error": "Failed to download binary", "url": url}

        raw_bytes, content_type, http_status = result
        return await ingestion_service.store_binary(
            enterprise_id=enterprise_id,
            research_job_id=research_job_id,
            research_query_id=query_id,
            url=url,
            raw_bytes=raw_bytes,
            content_type=content_type,
            http_status=http_status,
        )

    # --- PATH B: Web page — extract markdown via Tavily ----------------------
    markdown = await _extract_with_tavily(url)
    if markdown is None:
        return {"source_id": None, "error": "Failed to extract page content", "url": url}

    return await ingestion_service.store_page(
        enterprise_id=enterprise_id,
        research_job_id=research_job_id,
        research_query_id=query_id,
        url=url,
        markdown_content=markdown,
    )
