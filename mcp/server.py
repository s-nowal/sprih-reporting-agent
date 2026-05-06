"""MCP server exposing Sprih AI agents and the research data pipeline.

Connect from Claude Code, Claude Desktop, or Claude.ai to access Sprih's
backend agents and ESG research tools — Serper web search, Playwright-based
page crawling, PDF extraction, and a persistent bronze content store.

Surface
-------
Agent tools (autonomous — no further tool calls needed from the client):
    run_research(prompt)              -> full research report (markdown)

Manual research tools (step-by-step):
    sprih_search(query, num_results)  -> {search_query_id, results[...]}
    sprih_fetch(result_id)            -> {source_id, url, preview, ...}

Content library tools (previously downloaded sources):
    list_sources()                    -> [{source_id, url, source_type, fetched_at}]
    read_source(source_id)            -> full extracted markdown content
    read_source_meta(source_id)       -> meta.json sidecar as dict

Deploy
------
Local (stdio — default; Claude Code / Claude Desktop launch as subprocess):
    uv run python mcp/server.py

    claude mcp add sprih-research -- \
        uv run --directory /home/sachchit/sprih/sandbox python mcp/server.py

    Claude Desktop (~/.config/Claude/claude_desktop_config.json):
        {"mcpServers": {"sprih-research": {
            "command": "uv",
            "args": ["run", "--directory", "/home/sachchit/sprih/sandbox",
                     "python", "mcp/server.py"]
        }}}

Remote (streamable HTTP — exposed via pyngrok for Claude to hit over the network):
    # pyngrok reads the authtoken from ~/.config/ngrok/ngrok.yml if present
    # (e.g. set once via `ngrok config add-authtoken <token>`); otherwise set
    # NGROK_AUTHTOKEN in the process env.
    uv run python mcp/server.py --transport streamable-http --port 8765 --ngrok
    # Server prints:  MCP public URL: https://<subdomain>.ngrok-free.app/mcp
    # Register that URL with Claude:
    claude mcp add --transport http sprih-research \
        https://<subdomain>.ngrok-free.app/mcp

Notes
-----
The folder ``mcp/`` intentionally has no ``__init__.py``. Python's import
system (PEP 420) gives regular packages priority over namespace packages,
so the installed ``mcp`` SDK (site-packages) wins over this directory when
resolving ``from mcp.server.fastmcp import FastMCP``. Keeping the server
in a single file sidesteps any intra-package imports that would otherwise
trigger the shadow.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from uuid import uuid4

# --- Ensure project root is on sys.path for backend imports ------------------
# When run as ``python mcp/server.py`` the script dir (``mcp/``) is sys.path[0].
# Backend imports below require the project root, so prepend it explicitly.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from backend.ai.tools.web_fetch import fetch_url
from backend.ai.tools.web_search import search_web
from backend.config import settings
from backend.infra.registry import (
    Registry,
    get_db,
    get_storage,
    set_registry,
    teardown_registry,
)
from backend.models.data_source import DataSource
from backend.models.job import Job

logger = logging.getLogger("sprih.mcp")

# Synthetic identifiers for the single Job row that scopes this server run.
# Every web_search / web_fetch call in this process shares the same job_id,
# which gives the provenance chain (search_queries → search_results →
# data_sources) a valid FK target without requiring a real enterprise user.
_MCP_ENTERPRISE_ID = "mcp-local"
_MCP_JOB_ID: str | None = None


# ---------------------------------------------------------------------------
# Lifespan — initialise infra and create a session Job row
# ---------------------------------------------------------------------------


async def _ensure_mcp_job() -> str:
    """Create (once) a Job row scoped to this MCP server process.

    All search/fetch provenance rows link to this job_id. Idempotent — safe
    to call from multiple handlers; later calls return the cached ID.

    Returns:
        UUID of the session Job row.

    Raises:
        Exception: If the DB insert fails.
    """
    global _MCP_JOB_ID
    if _MCP_JOB_ID is not None:
        return _MCP_JOB_ID
    job_id = str(uuid4())
    db = get_db()
    async with db() as session:
        session.add(
            Job(
                id=job_id,
                enterprise_id=_MCP_ENTERPRISE_ID,
                thread_id=None,
                job_type="mcp_session",
                status="running",
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
    _MCP_JOB_ID = job_id
    logger.info("mcp session job created id=%s", job_id)
    return job_id


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
    """Boot the Registry + create a session Job; tear down on shutdown.

    Args:
        server: The FastMCP server instance (unused but required by the
            lifespan signature).

    Yields:
        A dict with ``job_id`` — available to handlers via
        ``ctx.request_context.lifespan_context`` if needed.
    """
    # Pre-create the engine singleton with echo=False before Registry.from_config
    # touches it. get_engine() is lazy — the first caller wins. If we don't do
    # this, settings.debug=True causes echo=True which makes SQLAlchemy reset
    # sqlalchemy.engine to INFO, flooding the MCP log stream with SQL noise.
    from backend.infra.db import get_engine as _get_engine
    _get_engine(echo=False)
    registry = await Registry.from_config(settings)
    set_registry(registry)
    job_id = await _ensure_mcp_job()
    try:
        yield {"job_id": job_id}
    finally:
        await teardown_registry()


mcp = FastMCP(
    "sprih",
    instructions=(
        "Sprih AI Platform — backend agents and ESG research pipeline. "
        "Prefer run_research(prompt) for any research task: it runs autonomously "
        "server-side and returns a complete markdown report without needing further "
        "tool calls. Use sprih_search then sprih_fetch only when you need manual "
        "control over individual pages. Use list_sources / read_source to access "
        "content that was already downloaded in a prior session."
    ),
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Tools — thin MCP adapters over backend.ai.tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def sprih_search(query: str, num_results: int = 5) -> dict[str, Any]:
    """Search Google via Serper and return ranked results with persistent IDs.

    Use this to find relevant web pages or documents before fetching their
    content with sprih_fetch. Do not use this if run_research suits the task —
    run_research calls search internally and returns a complete report.
    Do not pass raw URLs here; this tool only accepts search query strings.

    Args:
        query: Concise search query string (e.g. "EU CSRD 2024 scope 3
            requirements"). Use keywords, not full questions.
        num_results: Number of organic results to return (default 5, max 10).

    Returns:
        dict with:
        - ``search_query_id`` (str | None): UUID of the persisted query row.
        - ``results`` (list[dict]): Ranked results, each with ``result_id``
          (UUID — pass to sprih_fetch), ``url``, ``title``, ``snippet``,
          ``position``.
        - ``error`` (str): Present only on failure; results will be empty.
    """
    job_id = await _ensure_mcp_job()
    return await search_web(query=query, num_results=num_results, job_id=job_id)


@mcp.tool()
async def sprih_fetch(result_id: str) -> dict[str, Any]:
    """Download and extract the full content of a sprih_search result.

    Use this after sprih_search to retrieve and persist the complete text of
    a page or document. Handles web pages (Playwright/crawl4ai rendering) and
    binary files (PDF, XLSX, DOCX, CSV). The result is stored in bronze storage
    and can be re-read later with read_source(source_id).

    Do not use this with arbitrary URLs — result_id must be a UUID returned by
    sprih_search. Do not use this if run_research suits the task; it calls
    fetch internally.

    Args:
        result_id: UUID from a sprih_search result entry (not a URL, not a
            position number — must be the UUID string from ``result_id``).

    Returns:
        dict with ``source_id`` (UUID for read_source), ``source_type``,
        ``url``, ``preview`` (first ~2000 chars of extracted text),
        ``s3_bronze_path``. On failure contains ``error`` and
        ``source_id=None``.
    """
    job_id = await _ensure_mcp_job()
    return await fetch_url(result_id=result_id, job_id=job_id)


# ---------------------------------------------------------------------------
# Research agent tool — runs the full LangGraph research pipeline
# ---------------------------------------------------------------------------


@mcp.tool()
async def run_research(prompt: str) -> str:
    """Run the Sprih Research Agent and return a complete structured report.

    Executes the full research pipeline autonomously server-side: plans
    sub-queries, searches Google via Serper, fetches and extracts web pages
    and PDFs, then synthesises findings into a structured markdown report with
    a source index and data gaps section. No further tool calls are needed.

    Prefer this over calling sprih_search + sprih_fetch manually whenever the
    goal is a research report rather than inspection of a specific page.
    Do not use this for simple factual lookups — it is designed for multi-source
    ESG research tasks that require planning and synthesis.

    Note: typical runs take 2–10 minutes depending on scope.

    Args:
        prompt: Research brief as a user message (e.g. "Find ESG disclosures,
            certifications, and environmental metrics for Samarth Diamonds and
            its top 3 competitors. Return findings, data gaps, and sources.").

    Returns:
        Structured markdown research report including findings per topic,
        identified data gaps, and a numbered source index.
    """
    from langchain_core.messages import HumanMessage

    from backend.ai.agents.research_agent import build_research_graph

    job_id = await _ensure_mcp_job()
    graph = build_research_graph(checkpointer=None)
    result = await graph.ainvoke(
        {"messages": [HumanMessage(content=prompt)]},
        config={"configurable": {"job_id": job_id, "thread_id": str(uuid4())}},
    )
    last = result["messages"][-1]
    return last.content if hasattr(last, "content") else str(last)


# ---------------------------------------------------------------------------
# Storage tools — read-only views over bronze storage
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_sources() -> list[dict[str, Any]]:
    """List all web pages and documents previously downloaded to bronze storage.

    Use this to discover what content has already been fetched — including
    from prior sessions — before calling read_source or read_source_meta.
    Do not use this to search for new information; use sprih_search instead.

    Returns:
        List of dicts ordered newest-first, each with:
        - ``source_id`` (str): UUID to pass to read_source or read_source_meta.
        - ``url`` (str): Original URL of the fetched page or document.
        - ``source_type`` (str): e.g. ``web_page``, ``web_pdf``.
        - ``fetched_at`` (str | None): ISO-8601 timestamp of when it was fetched.
    """
    db = get_db()
    async with db() as session:
        stmt = select(DataSource).order_by(DataSource.created_at.desc())
        rows = (await session.execute(stmt)).scalars().all()
    return [
        {
            "source_id": r.id,
            "url": r.source_ref,
            "source_type": r.source_type,
            "fetched_at": r.fetched_at.isoformat() if r.fetched_at else None,
        }
        for r in rows
    ]


@mcp.tool()
async def read_source(source_id: str) -> str:
    """Read the full extracted text of a previously downloaded source.

    Use this after sprih_fetch (or list_sources) to read the complete content
    of a stored page or document. For web pages this is crawl4ai-cleaned
    markdown; for PDFs it is pymupdf-extracted text with ``## Page N``
    separators. Do not use this to fetch new content — call sprih_fetch first.

    Args:
        source_id: UUID from a sprih_fetch result or list_sources entry.

    Returns:
        Full markdown text of the source. Returns a short explanatory note
        if no text was extractable (e.g. scanned image-only PDF).

    Raises:
        ValueError: If source_id does not exist in the database.
    """
    db = get_db()
    async with db() as session:
        row = (
            await session.execute(select(DataSource).where(DataSource.id == source_id))
        ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"source {source_id!r} not found")

    storage = get_storage()
    content_path = f"{row.s3_bronze_path}content.md"
    if storage.exists(content_path):
        return storage.read_text(content_path)
    return (
        f"# {row.source_ref}\n\n"
        f"(no extracted text available — source_type={row.source_type})"
    )


@mcp.tool()
async def read_source_meta(source_id: str) -> dict[str, Any]:
    """Read the metadata sidecar for a previously downloaded source.

    Use this to inspect fetch details without loading the full content — useful
    for checking extraction_status, page count (PDFs), content_length, or the
    original URL before deciding whether to call read_source. Do not use this
    to read the actual text content; use read_source for that.

    Args:
        source_id: UUID from a sprih_fetch result or list_sources entry.

    Returns:
        Dict containing source_ref (URL), source_type, content_length, and
        fetched_at. PDFs also include page_count, extraction_status, and an
        image_manifest. Returns ``{"error": "meta.json missing", ...}`` if the
        sidecar file is absent.

    Raises:
        ValueError: If source_id does not exist in the database.
    """
    db = get_db()
    async with db() as session:
        row = (
            await session.execute(select(DataSource).where(DataSource.id == source_id))
        ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"source {source_id!r} not found")

    storage = get_storage()
    meta_path = f"{row.s3_bronze_path}meta.json"
    if storage.exists(meta_path):
        return json.loads(storage.read_text(meta_path))
    return {"error": "meta.json missing", "source_id": source_id}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    """Parse CLI args controlling the MCP transport.

    Returns:
        Namespace with ``transport`` (``stdio`` | ``sse`` | ``streamable-http``),
        ``host``, and ``port``. ``host`` / ``port`` are only honoured by the
        network transports.
    """
    parser = argparse.ArgumentParser(description="Sprih research MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default="stdio",
        help="MCP transport (default: stdio for local subprocess use)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8765, help="HTTP bind port")
    parser.add_argument(
        "--ngrok",
        action="store_true",
        help="Open a pyngrok tunnel to the HTTP port and print the public URL "
        "(uses the token from ~/.config/ngrok/ngrok.yml or NGROK_AUTHTOKEN; "
        "only valid with sse/streamable-http)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    # Configure logging before anything else runs.
    # force=True is required: FastMCP and SQLAlchemy install handlers at import
    # time, making a plain basicConfig() call a no-op.  force=True removes those
    # pre-installed handlers and installs ours instead, with stderr so the stdio
    # JSON-RPC stream on stdout stays clean.
    logging.basicConfig(
        level=logging.WARNING,
        stream=sys.stderr,
        format="%(levelname)s %(name)s: %(message)s",
        force=True,
    )
    # Silence noisy third-party loggers explicitly — their loggers may have
    # their own effective level set, so root-level WARNING alone is not enough.
    for _noisy in ("sqlalchemy", "sqlalchemy.engine", "httpx", "httpcore", "fastmcp"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
    # Re-enable our own server logger so startup/job messages remain visible.
    logging.getLogger("sprih.mcp").setLevel(logging.INFO)

    if args.ngrok and args.transport == "stdio":
        sys.exit("--ngrok requires --transport sse or streamable-http")

    # FastMCP reads host/port from constructor settings for network transports.
    tunnel = None
    if args.transport in ("sse", "streamable-http"):
        mcp.settings.host = args.host
        mcp.settings.port = args.port

        if args.ngrok:
            # Lazy imports so these are only required when the flag is used.
            from mcp.server.transport_security import TransportSecuritySettings
            from pyngrok import ngrok as _ngrok

            tunnel = _ngrok.connect(args.port, "http")

            # FastMCP's transport middleware refuses requests whose Host header
            # isn't in its allow-list (default: localhost/127.0.0.1) to block
            # DNS-rebinding attacks. The ngrok public hostname must be added or
            # every request is answered with "421 Misdirected Request".
            tunnel_host = urlparse(tunnel.public_url).netloc
            mcp.settings.transport_security = TransportSecuritySettings(
                allowed_hosts=[tunnel_host],
                allowed_origins=[tunnel.public_url],
            )

            mcp_path = "/mcp" if args.transport == "streamable-http" else "/sse"
            print(
                f"MCP public URL: {tunnel.public_url}{mcp_path}",
                file=sys.stderr,
                flush=True,
            )

    try:
        mcp.run(transport=args.transport)
    finally:
        if tunnel is not None:
            from pyngrok import ngrok as _ngrok

            _ngrok.disconnect(tunnel.public_url)
            _ngrok.kill()
