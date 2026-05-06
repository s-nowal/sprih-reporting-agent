"""Web fetch tool — fetches a URL and delegates persistence to ingestion_service.

Routing:
- Binary URLs (.pdf, .xlsx, …): downloaded as raw bytes via httpx.
- Web pages (HTML / JS): crawled via crawl4ai (Playwright-based), which handles
  JS rendering and returns clean markdown.

The tool itself only fetches — all storage writes and DB operations are
handled by ``ingestion_service``. URL resolution from ``result_id`` is
handled by ``search_service``.

Two surfaces share one implementation:
- ``fetch_url(result_id, job_id)``: plain async function — callable from
  LangGraph, the MCP server, a script, anywhere. Returns the raw artifact
  dict.
- ``web_fetch``: the LangChain ``@tool`` wrapper that reads ``job_id`` from
  ``RunnableConfig.configurable``, forwards to ``fetch_url``, and formats
  the agent-facing ``(content, artifact)`` tuple.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from backend.services import ingestion_service, search_service

logger = logging.getLogger(__name__)

_BINARY_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc")

# Maximum characters of extracted content returned to the agent in the
# ToolMessage.content field. Full content is stored in S3 (artifact side).
_AGENT_EXCERPT_LENGTH = 2000


def _format_tool_content(url: str, result: dict[str, Any]) -> str:
    """Format the text content returned to the agent in the tool message.

    Produces a structured block the agent can use directly for citation and
    synthesis: source metadata header followed by the fetched text excerpt.

    Args:
        url: The fetched URL.
        result: Storage result dict from ingestion_service (contains
            ``source_id``, ``source_type``, ``preview``, optionally
            ``duplicate`` and ``error``).

    Returns:
        Formatted string with source header and content excerpt.
    """
    source_id = result.get("source_id", "unknown")
    source_type = result.get("source_type", "unknown")
    preview = result.get("preview", "")
    header = (
        f"SOURCE STORED\n"
        f"source_id: {source_id}\n"
        f"source_type: {source_type}\n"
        f"url: {url}\n"
    )
    if result.get("error"):
        return header + f"\nError: {result['error']}"
    suffix = "(cached — reusing stored copy)\n\n" if result.get("duplicate") else ""
    if preview:
        return header + f"\nCONTENT EXCERPT:\n{suffix}{preview[:_AGENT_EXCERPT_LENGTH]}"
    return header + f"\n{suffix}(no content available)"


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
    1. Resolve ``result_id`` → URL via ``search_service``.
    2. Global dedup check via ``ingestion_service.check_duplicate``.
    3. Download (httpx for binaries, crawl4ai for web pages).
    4. Persist to bronze storage + ``data_sources`` row via ``ingestion_service``.

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
    search_result = await search_service.get_search_result(result_id)
    if search_result is None:
        return {
            "source_id": None,
            "error": f"result_id {result_id!r} not found",
            "url": None,
        }
    url = search_result["url"]

    # --- Global deduplication: skip if any job has already fetched this URL --
    dup = await ingestion_service.check_duplicate(url)
    if dup:
        return {**dup, "url": url}

    # --- PATH A: Binary content (PDF, Excel, etc.) ---------------------------
    if _is_binary_url(url):
        download = await _download_binary(url)
        if download is None:
            return {"source_id": None, "error": "Failed to download binary", "url": url}

        raw_bytes, content_type, http_status = download
        result = await ingestion_service.store_binary(
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

    result = await ingestion_service.store_page(
        job_id=job_id,
        search_result_id=result_id,
        url=url,
        markdown_content=markdown,
    )
    return {**result, "url": url}


@tool(response_format="content_and_artifact")
async def web_fetch(
    result_id: str,
    *,
    config: RunnableConfig,
) -> tuple[str, dict[str, Any]]:
    """Download and store the full content of a search result for later analysis.

    Use this after ``web_search`` to retrieve the complete content of a page or
    document. Pass the ``result_id`` from a ``web_search`` result — the URL is
    resolved from the database, so the agent never needs to handle raw URLs.
    Handles both web pages (HTML/JS rendered via Playwright) and binary files
    (PDF, XLSX, etc.).

    Returns two parts via the ``content_and_artifact`` pattern:
    - ``content`` (str): Source metadata header + text excerpt for the agent
      to read and synthesize. PDFs include extracted text; web pages include
      cleaned markdown. Stored in ``ToolMessage.content`` and fed to the LLM.
    - ``artifact`` (dict): Full storage metadata (``source_id``,
      ``s3_bronze_path``, ``source_type``, ``preview``). Stored in
      ``ToolMessage.artifact`` and also fed to the LLM as part of the tool
      message payload.

    Args:
        result_id: The ``result_id`` from a ``web_search`` result entry.

    Returns:
        Tuple of ``(content, artifact)`` where ``content`` is the agent-readable
        string and ``artifact`` is the raw storage result dict.
    """
    job_id: str | None = config.get("configurable", {}).get("job_id")
    result = await fetch_url(result_id=result_id, job_id=job_id)
    url = result.get("url") or ""
    return _format_tool_content(url, result), result
