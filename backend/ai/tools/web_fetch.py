"""Web fetch tool — fetches a URL and delegates persistence to ingestion_service.

Routing:
- Binary URLs (.pdf, .xlsx, …): downloaded as raw bytes via httpx.
- Web pages (HTML / JS): crawled via crawl4ai (Playwright-based), which handles
  JS rendering and returns clean markdown.

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

_BINARY_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc")


def _is_binary_url(url: str) -> bool:
    """Heuristic: does the URL path end with a known binary extension?

    Args:
        url: The URL to inspect.

    Returns:
        ``True`` if the URL ends with a binary file extension.
    """
    return any(url.lower().endswith(ext) for ext in _BINARY_EXTENSIONS)


async def _download_binary(url: str) -> tuple[bytes, str, int] | None:
    """Download a binary file (PDF, XLSX, etc.) via httpx.

    Follows redirects and enforces a 30-second timeout.

    Args:
        url: The URL pointing to a downloadable binary file.

    Returns:
        A tuple of ``(raw_bytes, content_type, http_status)`` on success,
        or ``None`` if the request failed for any reason.
    """
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            return resp.content, resp.headers.get("content-type", ""), resp.status_code
    except Exception as e:
        logger.warning("Binary download failed for %s: %s", url, e)
        return None


async def _crawl_page(url: str) -> str | None:
    """Crawl a web page with crawl4ai and return its content as markdown.

    Uses ``AsyncWebCrawler`` (Playwright-based) so JS-rendered pages are
    handled correctly. Returns ``fit_markdown`` when available (boilerplate
    stripped), falling back to ``raw_markdown``.

    Args:
        url: The web page URL to crawl.

    Returns:
        Markdown string of the main page content, or ``None`` on failure.
    """
    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)

        if not result.success:
            logger.warning("crawl4ai failed for %s: %s", url, result.error_message)
            return None

        # result.markdown may be a MarkdownGenerationResult object or a plain str
        md = result.markdown
        if hasattr(md, "fit_markdown"):
            return md.fit_markdown or md.raw_markdown
        return md or None
    except Exception as e:
        logger.warning("crawl4ai raised for %s: %s", url, e)
        return None


@tool
async def web_fetch(
    result_id: str,
    *,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Download and store the full content of a search result for later analysis.

    Use this after ``web_search`` to retrieve the complete content of a page or
    document. Pass the ``result_id`` from a ``web_search`` result — the URL is
    resolved from the database, so the agent never needs to handle raw URLs.
    Handles both web pages (HTML/JS rendered via Playwright) and binary files
    (PDF, XLSX, etc.).

    Args:
        result_id: The ``result_id`` from a ``web_search`` result entry.

    Returns:
        dict with keys:
        - ``source_id`` (str | None): UUID of the stored source, or ``None`` on failure.
        - ``s3_bronze_path`` (str): Storage path where content was saved.
        - ``source_type`` (str): Detected type, e.g. ``"web_page"`` or ``"web_pdf"``.
        - ``preview`` (str): First 500 characters of content.
        - ``duplicate`` (bool): ``True`` if this URL was already fetched in this job.
        - ``error`` (str): Present only on failure, describes what went wrong.
    """
    # --- Read per-request config from LangGraph configurable -----------------
    enterprise_id: str = config.get("configurable", {}).get(
        "enterprise_id", "dev-enterprise"
    )
    job_id: str | None = config.get("configurable", {}).get("job_id")

    # --- Resolve URL from the stored search result ---------------------------
    search_result = await ingestion_service.get_search_result(result_id)
    if search_result is None:
        return {"source_id": None, "error": f"result_id {result_id!r} not found."}
    url = search_result["url"]

    # --- Deduplication: skip if same URL already fetched ---------------------
    dup = await ingestion_service.check_duplicate(url, job_id)
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
            job_id=job_id,
            search_result_id=result_id,
            url=url,
            raw_bytes=raw_bytes,
            content_type=content_type,
            http_status=http_status,
        )

    # --- PATH B: Web page — crawl via crawl4ai (Playwright) ------------------
    markdown = await _crawl_page(url)
    if markdown is None:
        return {"source_id": None, "error": "Failed to crawl page", "url": url}

    return await ingestion_service.store_page(
        enterprise_id=enterprise_id,
        job_id=job_id,
        search_result_id=result_id,
        url=url,
        markdown_content=markdown,
    )
