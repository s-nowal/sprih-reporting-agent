"""Crawl service — fetch and download pipeline for web content.

Owns the two fetch paths (binary download via httpx, web crawl via crawl4ai)
and the ``fetch_url`` entry point that routes between them.

URL resolution from ``result_id`` is delegated to ``ingestion.search``.
Bronze storage writes and DB operations are delegated to ``ingestion.store``.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from backend.services.ingestion import search, store

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


async def fetch_url(
    result_id: str,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Resolve a ``result_id`` to its URL, fetch the content, and persist it.

    Handles the full fetch pipeline:
    1. Resolve ``result_id`` → URL via ``search.get_search_result``.
    2. Global dedup check via ``store.check_duplicate``.
    3. Download (httpx for binaries, crawl4ai for web pages).
    4. Persist to bronze storage + ``data_sources`` row via ``store``.

    Args:
        result_id: UUID of a ``search_results`` row from a prior ``web_search``.
        job_id: FK to the parent job (tracks which run triggered the fetch).
            May be ``None`` for one-off / out-of-flow fetches.

    Returns:
        Dict with ``source_id``, ``source_type``, ``s3_bronze_path``,
        ``preview``, and ``url``. On cache hit also includes ``duplicate=True``.
        On failure contains ``error`` and ``source_id=None``.
    """
    # --- Resolve URL from the stored search result ---------------------------
    search_result = await search.get_search_result(result_id)
    if search_result is None:
        return {
            "source_id": None,
            "error": f"result_id {result_id!r} not found",
            "url": None,
        }
    url = search_result["url"]

    # --- Global deduplication: skip if any job has already fetched this URL --
    dup = await store.check_duplicate(url)
    if dup:
        return {**dup, "url": url}

    # --- PATH A: Binary content (PDF, Excel, etc.) ---------------------------
    if _is_binary_url(url):
        download = await _download_binary(url)
        if download is None:
            return {"source_id": None, "error": "Failed to download binary", "url": url}

        raw_bytes, content_type, http_status = download
        result = await store.store_binary(
            job_id=job_id,
            search_result_id=result_id,
            url=url,
            raw_bytes=raw_bytes,
            content_type=content_type,
            http_status=http_status,
        )
        return {**result, "url": url}

    # --- PATH B: Web page — crawl via crawl4ai (Playwright) ------------------
    markdown = await _crawl_page(url)
    if markdown is None:
        return {"source_id": None, "error": "Failed to crawl page", "url": url}

    result = await store.store_page(
        job_id=job_id,
        search_result_id=result_id,
        url=url,
        markdown_content=markdown,
    )
    return {**result, "url": url}
