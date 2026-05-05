"""Web fetch tool — fetches a URL and delegates persistence to ingestion_service.

Routing:
- Binary URLs (.pdf, .xlsx, …): downloaded as raw bytes via httpx.
- Web pages (HTML / JS): crawled via crawl4ai (Playwright-based), which handles
  JS rendering and returns clean markdown.

The tool itself only fetches — all storage writes and DB operations are
handled by ``ingestion_service``. URL resolution from ``result_id`` is
handled by ``search_service``.

After each successful fetch a local copy is also written to
``agent_folder/workspace/research/`` so the reporting agent can read it
directly from the filesystem without going through the vector store.
"""

from __future__ import annotations
import logging
import posixpath
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from backend.services import ingestion_service, search_service

logger = logging.getLogger(__name__)
_BINARY_EXTENSIONS = (".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc")
_AGENT_EXCERPT_LENGTH = 2000

# agent_folder lives four levels above this file: backend/ai/tools/web_fetch.py
_RESEARCH_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "agent_folder"
    / "workspace"
    / "research"
)

def _save_to_research(source_id: str, filename: str, content: bytes | str) -> None:
    """Write fetched content into the local research workspace folder.

    Creates ``agent_folder/workspace/research/`` if it does not exist, then
    writes ``content`` to ``{research_dir}/{filename}``.  Errors are logged but
    never raised so a filesystem failure cannot abort the fetch.

    Args:
        source_id: Ingestion source id — used only for log messages.
        filename: Target filename inside the research directory.
        content: Raw bytes (binary files) or a string (markdown pages).
    """
    try:
        _RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
        dest = _RESEARCH_DIR / filename
        if isinstance(content, bytes):
            dest.write_bytes(content)
        else:
            dest.write_text(content, encoding="utf-8")
        logger.info("Saved research artifact %s → %s", source_id, dest)
    except Exception as exc:
        logger.warning("Failed to save research artifact %s: %s", source_id, exc)


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


async def _try_crawl4ai(url: str) -> str | None:
    """Attempt to crawl ``url`` with crawl4ai (Playwright-based).

    Returns markdown on success, ``None`` on any failure so the caller can
    try the httpx fallback.

    Args:
        url: The web page URL to crawl.

    Returns:
        Cleaned markdown string or ``None``.
    """
    try:
        from crawl4ai import AsyncWebCrawler

        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)

        if not result.success:
            logger.warning("crawl4ai failed for %s: %s", url, result.error_message)
            return None

        md = result.markdown
        if hasattr(md, "fit_markdown"):
            return md.fit_markdown or md.raw_markdown
        return md or None
    except Exception as exc:
        logger.warning("crawl4ai raised for %s: %s", url, exc)
        return None


async def _try_httpx_markitdown(url: str) -> str | None:
    """Fetch ``url`` with httpx and convert the HTML to markdown via MarkItDown.

    Used as a fallback when crawl4ai / Playwright is unavailable (e.g. on
    Windows where ``asyncio.ProactorEventLoop`` cannot spawn subprocesses).

    Args:
        url: The web page URL to fetch.

    Returns:
        Markdown string or ``None`` on failure.
    """
    import os
    import tempfile
    from markitdown import MarkItDown

    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=30.0,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ESGBot/1.0)"},
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html_bytes = resp.content

        with tempfile.NamedTemporaryFile(delete=False, suffix=".html") as tmp:
            tmp.write(html_bytes)
            tmp_path = tmp.name

        try:
            result = MarkItDown().convert(tmp_path)
            return result.text_content or None
        finally:
            os.remove(tmp_path)

    except Exception as exc:
        logger.warning("httpx/markitdown fallback failed for %s: %s", url, exc)
        return None


async def _crawl_page(url: str) -> str | None:
    """Return page content as markdown, trying crawl4ai then httpx+MarkItDown.

    crawl4ai (Playwright) is tried first for full JS rendering. If it raises
    or reports failure — common on Windows where ``ProactorEventLoop`` cannot
    spawn subprocesses — the call falls back to a plain httpx GET converted
    to markdown by MarkItDown.

    Args:
        url: The web page URL to crawl.

    Returns:
        Markdown string of the main page content, or ``None`` if both methods
        fail.
    """
    markdown = await _try_crawl4ai(url)
    if markdown is not None:
        return markdown
    logger.info("crawl4ai unavailable for %s, trying httpx/markitdown fallback", url)
    return await _try_httpx_markitdown(url)


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
    # --- Read per-request config from LangGraph configurable -----------------
    job_id: str | None = config.get("configurable", {}).get("job_id")

    # --- Resolve URL from the stored search result ---------------------------
    search_result = await search_service.get_search_result(result_id)
    if search_result is None:
        error_msg = f"result_id {result_id!r} not found."
        return error_msg, {"source_id": None, "error": error_msg}
    url = search_result["url"]

    # --- Global deduplication: skip if any job has already fetched this URL --
    dup = await ingestion_service.check_duplicate(url)
    if dup:
        return _format_tool_content(url, dup), dup

    # --- PATH A: Binary content (PDF, Excel, etc.) ---------------------------
    if _is_binary_url(url):
        download = await _download_binary(url)
        if download is None:
            artifact: dict[str, Any] = {
                "source_id": None, "error": "Failed to download binary", "url": url
            }
            return f"Error: failed to download binary from {url}", artifact

        raw_bytes, content_type, http_status = download
        result = await ingestion_service.store_binary(
            job_id=job_id,
            search_result_id=result_id,
            url=url,
            raw_bytes=raw_bytes,
            content_type=content_type,
            http_status=http_status,
        )
        url_filename = posixpath.basename(urlparse(url).path)
        bin_filename = url_filename or f"{result.get('source_id', result_id)}.bin"
        _save_to_research(result.get("source_id", result_id), bin_filename, raw_bytes)
        return _format_tool_content(url, result), result

    # --- PATH B: Web page — crawl via crawl4ai (Playwright) ------------------
    markdown = await _crawl_page(url)
    if markdown is None:
        artifact = {"source_id": None, "error": "Failed to crawl page", "url": url}
        return f"Error: failed to crawl {url}", artifact

    result = await ingestion_service.store_page(
        job_id=job_id,
        search_result_id=result_id,
        url=url,
        markdown_content=markdown,
    )
    page_filename = f"{result.get('source_id', result_id)}.md"
    _save_to_research(result.get("source_id", result_id), page_filename, markdown)
    return _format_tool_content(url, result), result
