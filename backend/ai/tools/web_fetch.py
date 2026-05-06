"""Web fetch tool — thin ``@tool`` wrapper over ``services/ingestion/crawl.fetch_url``.

All pipeline logic (binary download, crawl4ai crawling, dedup, bronze storage)
lives in ``backend.services.ingestion.crawl``. This module owns only:
- ``_format_tool_content``: formats the agent-facing tool message string.
- ``web_fetch``: the LangChain ``@tool`` wrapper that reads config and delegates.

``fetch_url`` is re-exported here so ``mcp/server.py`` imports remain unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from backend.services.ingestion.crawl import fetch_url  # noqa: F401 — re-exported for mcp/server.py

logger = logging.getLogger(__name__)

# Maximum characters of extracted content returned to the agent in the
# ToolMessage.content field. Full content is stored in S3 (artifact side).
_AGENT_EXCERPT_LENGTH = 2000


def _format_tool_content(url: str, result: dict[str, Any]) -> str:
    """Format the text content returned to the agent in the tool message.

    Produces a structured block the agent can use directly for citation and
    synthesis: source metadata header followed by the fetched text excerpt.

    Args:
        url: The fetched URL.
        result: Storage result dict from ingestion.store (contains
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
