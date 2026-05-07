"""Bronze storage service — persists crawled content to S3 and the DB.

Owns the bronze storage pipeline:
- ``store_page``: save web page markdown to bronze + create ``data_sources`` row
- ``store_binary``: save binary file (PDF, XLSX, …) to bronze + create ``data_sources`` row
- ``check_duplicate``: skip re-fetching a URL that has already been stored
- ``copy_source_to_workspace``: copy a fetched source's original bytes from
  bronze into a thread's ``research/citations/`` folder so the user can open
  the file from Drive next to the report.

Search query provenance (recording queries, resolving result IDs) lives in
``ingestion.search``. This service is agent-agnostic.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote, urlparse
from uuid import uuid4

from sqlalchemy import select

from backend.infra.registry import get_db, get_storage
from backend.models.data_source import DataSource

logger = logging.getLogger(__name__)

PREVIEW_LENGTH = 2000


def _extract_pdf_sync(
    raw_bytes: bytes,
) -> tuple[str, int, list[tuple[int, int, str, bytes, int, int]]]:
    """Extract text and images from a PDF synchronously using pymupdf.

    Intended to run in a thread via ``asyncio.to_thread`` so it doesn't block
    the event loop. Processes every page of the document.

    Args:
        raw_bytes: Raw binary content of the PDF file.

    Returns:
        A 3-tuple of:
        - ``full_text`` (str): All pages concatenated with ``## Page N``
          section headers. Empty string if extraction fails.
        - ``page_count`` (int): Total number of pages in the PDF.
        - ``images`` (list): One entry per extracted image:
          ``(page_num, img_idx, ext, img_bytes, width, height)``
          where ``ext`` is e.g. ``"png"`` and ``img_bytes`` is raw image data.

    Raises:
        Does not raise — all exceptions are caught and logged. Returns empty
        text and empty image list on failure.
    """
    try:
        import pymupdf  # type: ignore
    except ImportError:
        logger.warning("pymupdf not installed — PDF text extraction unavailable")
        return "", 0, []

    try:
        doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
        pages_text: list[str] = []
        images: list[tuple[int, int, str, bytes, int, int]] = []

        for page_num, page in enumerate(doc, start=1):  # type: ignore[attr-defined]
            # --- Extract page text -------------------------------------------
            text = page.get_text()
            if text.strip():
                pages_text.append(f"## Page {page_num}\n\n{text.strip()}")

            # --- Extract embedded images -------------------------------------
            for img_idx, img_ref in enumerate(page.get_images(full=True)):
                xref = img_ref[0]
                try:
                    base_image = doc.extract_image(xref)
                    images.append((
                        page_num,
                        img_idx,
                        base_image["ext"],
                        base_image["image"],
                        base_image.get("width", 0),
                        base_image.get("height", 0),
                    ))
                except Exception as img_err:
                    logger.debug(
                        "Skipping image xref=%d page=%d: %s", xref, page_num, img_err
                    )

        page_count = len(doc)
        doc.close()
        return "\n\n".join(pages_text), page_count, images
    except Exception as e:
        logger.warning("PDF extraction failed: %s", e)
        return "", 0, []


async def check_duplicate(source_ref: str) -> dict[str, Any] | None:
    """Check if a public URL has already been fetched by any job or enterprise.

    Web-fetched content is always stored as public (``enterprise_id=NULL``),
    so deduplication is global — if any job has already fetched this URL the
    stored copy can be reused without re-downloading.

    Args:
        source_ref: The URL to check.

    Returns:
        A dict with ``source_id``, ``s3_bronze_path``, ``source_type``,
        ``preview``, and ``duplicate=True`` if a match is found.
        ``None`` if no duplicate exists or the check fails.
    """
    try:
        db = get_db()
        async with db() as session:
            stmt = select(DataSource).where(
                DataSource.source_ref == source_ref,
                DataSource.enterprise_id.is_(None),
            )
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()
            if row is None:
                return None
            # --- Load actual content preview from bronze storage ---------------
            storage = get_storage()
            preview = ""
            content_path = f"{row.s3_bronze_path}content.md"
            try:
                if storage.exists(content_path):
                    preview = storage.read_text(content_path)[:PREVIEW_LENGTH].strip()
            except Exception as _e:
                logger.debug("Could not read cached content for %s: %s", source_ref, _e)
            return {
                "source_id": row.id,
                "s3_bronze_path": row.s3_bronze_path,
                "source_type": row.source_type,
                "preview": preview,
                "duplicate": True,
            }
    except Exception as e:
        logger.warning("Dedup check failed: %s", e)
        return None


async def store_page(
    job_id: str | None,
    search_result_id: str | None,
    url: str,
    markdown_content: str,
) -> dict[str, Any]:
    """Save a crawled web page to public bronze storage and record it in the DB.

    Web-fetched content is always public (``enterprise_id=NULL``) and stored
    under ``public/bronze/{source_id}/``. Any enterprise can reuse it once
    ingested; access control is enforced at the silver/KG layer.

    Writes ``content.md`` and ``meta.json`` to the bronze directory, then
    creates a ``data_sources`` row linking the file to its provenance chain.

    Args:
        job_id: FK to the parent job (tracks which run triggered the fetch).
        search_result_id: FK to the ``search_results`` row that led to this fetch
            (``None`` if fetched outside of a search flow).
        url: The original page URL (stored as ``source_ref``).
        markdown_content: The page content already converted to markdown.

    Returns:
        dict with ``source_id``, ``s3_bronze_path``, ``source_type``, ``preview``.
    """
    source_id = str(uuid4())
    now = datetime.now(timezone.utc)
    storage = get_storage()

    # --- Write content + metadata sidecar to public bronze -------------------
    bronze_dir = f"public/bronze/{source_id}"
    storage.write_text(f"{bronze_dir}/content.md", markdown_content)

    meta = {
        "source_ref": url,
        "source_type": "web_page",
        "content_length": len(markdown_content),
        "crawled_at": now.isoformat(),
    }
    storage.write_text(f"{bronze_dir}/meta.json", json.dumps(meta, indent=2))

    # --- Create data_sources row (enterprise_id=NULL → public) ---------------
    s3_bronze_path = f"{bronze_dir}/"
    try:
        db = get_db()
        async with db() as session:
            session.add(
                DataSource(
                    id=source_id,
                    enterprise_id=None,
                    job_id=job_id,
                    search_result_id=search_result_id,
                    source_type="web_page",
                    source_ref=url,
                    s3_bronze_path=s3_bronze_path,
                    status="fetched",
                    fetched_at=now,
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning("Failed to persist data_source for %s: %s", url, e)

    preview = markdown_content[:PREVIEW_LENGTH].strip()
    return {
        "source_id": source_id,
        "s3_bronze_path": s3_bronze_path,
        "source_type": "web_page",
        "preview": preview,
    }


async def store_binary(
    job_id: str | None,
    search_result_id: str | None,
    url: str,
    raw_bytes: bytes,
    content_type: str,
    http_status: int,
) -> dict[str, Any]:
    """Save a downloaded binary file to public bronze storage and record it in the DB.

    Web-fetched binaries are always public (``enterprise_id=NULL``) and stored
    under ``public/bronze/{source_id}/``.

    For PDFs, runs inline text and image extraction via pymupdf:
    - Extracted text is stored as ``content.md`` alongside the original binary.
    - Embedded images are stored under ``images/page_{n}_img_{i}.{ext}``.
    - Page count and image metadata are recorded in ``meta.json``.

    For other binary types (XLSX, CSV, DOCX), only the raw file is stored;
    extraction is handled separately by the Extraction Agent.

    Args:
        job_id: FK to the parent job (tracks which run triggered the fetch).
        search_result_id: FK to the ``search_results`` row that led to this fetch.
        url: The original download URL (stored as ``source_ref``).
        raw_bytes: The raw binary content.
        content_type: HTTP Content-Type header value.
        http_status: HTTP status code from the download.

    Returns:
        dict with ``source_id``, ``s3_bronze_path``, ``source_type``, ``preview``.
        For PDFs, ``preview`` contains the first ``PREVIEW_LENGTH`` characters of
        extracted text. For other types, it is a human-readable size message.
    """
    source_id = str(uuid4())
    now = datetime.now(timezone.utc)
    storage = get_storage()

    # --- Determine file extension and source type ----------------------------
    ext = url.rsplit(".", 1)[-1].lower() if "." in url else "bin"
    source_type = f"web_{ext}"  # web_pdf, web_xlsx, etc.

    # --- Write original binary to public bronze storage ----------------------
    bronze_dir = f"public/bronze/{source_id}"
    storage.write(f"{bronze_dir}/original.{ext}", raw_bytes)

    # --- For PDFs: extract full text + images --------------------------------
    page_count = 0
    image_meta: list[dict] = []
    if ext == "pdf":
        full_text, page_count, raw_images = await asyncio.to_thread(
            _extract_pdf_sync, raw_bytes
        )
        if full_text:
            storage.write_text(f"{bronze_dir}/content.md", full_text)
            extraction_status = "extracted"
        elif page_count > 0:
            # PDF opened and pages found, but no extractable text —
            # likely an image-based or scanned document.
            extraction_status = "image_only"
        else:
            # pymupdf could not process the PDF at all (corrupt,
            # password-protected, or pymupdf not installed).
            extraction_status = "failed"
        for pg, idx, img_ext, img_bytes, w, h in raw_images:
            img_path = f"{bronze_dir}/images/page_{pg}_img_{idx}.{img_ext}"
            try:
                storage.write(img_path, img_bytes)
                image_meta.append(
                    {"page": pg, "index": idx, "path": img_path, "ext": img_ext,
                     "width": w, "height": h}
                )
            except Exception as e:
                logger.warning(
                    "Failed to store image page=%d idx=%d for %s: %s", pg, idx, url, e
                )
        preview = (
            full_text[:PREVIEW_LENGTH].strip()
            if full_text
            else f"(PDF downloaded, {len(raw_bytes)} bytes — text extraction failed)"
        )
    else:
        full_text = ""
        preview = f"({ext.upper()} downloaded, {len(raw_bytes)} bytes — pending extraction)"

    # --- Write metadata sidecar ----------------------------------------------
    meta: dict[str, Any] = {
        "source_ref": url,
        "source_type": source_type,
        "http_status": http_status,
        "content_type": content_type,
        "content_length": len(raw_bytes),
        "crawled_at": now.isoformat(),
    }
    if ext == "pdf":
        meta["pages"] = page_count
        meta["images"] = image_meta
        meta["extraction_status"] = extraction_status
    storage.write_text(f"{bronze_dir}/meta.json", json.dumps(meta, indent=2))

    # --- Create data_sources row (enterprise_id=NULL → public) ---------------
    s3_bronze_path = f"{bronze_dir}/"
    try:
        db = get_db()
        async with db() as session:
            session.add(
                DataSource(
                    id=source_id,
                    enterprise_id=None,
                    job_id=job_id,
                    search_result_id=search_result_id,
                    source_type=source_type,
                    source_ref=url,
                    s3_bronze_path=s3_bronze_path,
                    status="fetched",
                    fetched_at=now,
                )
            )
            await session.commit()
    except Exception as e:
        logger.warning("Failed to persist data_source for %s: %s", url, e)

    return {
        "source_id": source_id,
        "s3_bronze_path": s3_bronze_path,
        "source_type": source_type,
        "preview": preview,
    }


# ---------------------------------------------------------------------------
# Citation copy — bronze → workspace research/citations/
# ---------------------------------------------------------------------------

_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_basename(value: str) -> str:
    """Replace filesystem-unfriendly characters in a filename with underscores.

    Args:
        value: Candidate basename (already URL-decoded).

    Returns:
        A name containing only ``[A-Za-z0-9._-]`` runs, with collapsed
        underscores trimmed at the edges.
    """
    cleaned = _FILENAME_SAFE.sub("_", value).strip("._")
    return cleaned or ""


def _derive_citation_filename(
    source_id: str, source_ref: str, source_type: str
) -> str:
    """Build a human-friendly filename for a cited source.

    Strategy: take the URL's basename (URL-decoded, sanitized), prepend a
    short ``source_id`` prefix to avoid collisions, and ensure the extension
    matches the source type. Falls back to ``{prefix}_source.{ext}`` when the
    URL has no usable basename (e.g. ``https://example.com/about``).

    Args:
        source_id: UUID of the ``data_sources`` row.
        source_ref: Original URL that was fetched.
        source_type: ``"web_page"`` (markdown) or ``"web_<ext>"`` (binary).

    Returns:
        Basename suitable for ``research/citations/<basename>``.
    """
    short = source_id.replace("-", "")[:8]

    # --- Determine target extension ----------------------------------------
    if source_type == "web_page":
        target_ext = "md"
    elif source_type.startswith("web_"):
        target_ext = source_type.split("_", 1)[1] or "bin"
    else:
        target_ext = "bin"

    # --- Pull a usable basename from the URL -------------------------------
    parsed = urlparse(source_ref)
    raw = unquote((parsed.path or "").rsplit("/", 1)[-1]) or parsed.netloc
    base = _sanitize_basename(raw)

    if not base:
        return f"{short}_source.{target_ext}"

    # If the basename already ends with the desired extension, keep it; else
    # append the extension so Drive can pick the right viewer.
    if "." in base:
        stem, _, ext = base.rpartition(".")
        if ext.lower() == target_ext.lower():
            return f"{short}_{stem}.{ext}"
        return f"{short}_{stem}_{ext}.{target_ext}"
    return f"{short}_{base}.{target_ext}"


def _bronze_content_key(s3_bronze_path: str, source_type: str) -> str:
    """Compute the storage key of the original bytes for a fetched source.

    Web pages are stored as ``content.md``; binaries are stored as
    ``original.<ext>`` where ``<ext>`` is the suffix of ``source_type``.

    Args:
        s3_bronze_path: Bronze directory key from ``data_sources`` row,
            including its trailing slash.
        source_type: ``"web_page"`` or ``"web_<ext>"``.

    Returns:
        Storage-relative key of the original-bytes file in bronze.
    """
    if source_type == "web_page":
        return f"{s3_bronze_path}content.md"
    ext = source_type.split("_", 1)[1] if "_" in source_type else "bin"
    return f"{s3_bronze_path}original.{ext}"


async def copy_source_to_workspace(
    source_id: str,
    *,
    enterprise_id: str,
    thread_id: str,
    job_id: str | None,
) -> dict[str, Any]:
    """Copy a cited source's original bytes from bronze into ``research/citations/``.

    Enforces two scoping rules so the agent can't cite arbitrary historical
    content:
    - The ``DataSource`` row must be public (``enterprise_id IS NULL``) or
      belong to the calling enterprise.
    - The row's ``job_id`` must equal the current run's ``job_id`` — i.e. the
      source must have been fetched during this run.

    Idempotent: if the destination key already exists, returns success
    without re-reading bronze or rewriting.

    Args:
        source_id: ``data_sources.id`` of the source to cite.
        enterprise_id: Tenant id of the calling agent.
        thread_id: Thread id of the calling agent (scopes the destination).
        job_id: Current run's job id; sources fetched outside this job are
            rejected. ``None`` (no active job) always rejects.

    Returns:
        Dict with ``path`` (workspace-relative virtual path),
        ``size_bytes``, ``source_ref``, ``source_type``, and
        ``already_existed: bool`` on success. Returns a dict with ``error``
        on validation/lookup failure (the calling tool surfaces this to the
        agent as a tool message).
    """
    # --- Lookup -------------------------------------------------------------
    db = get_db()
    async with db() as session:
        row = await session.get(DataSource, source_id)
        if row is None:
            return {"error": f"source_id {source_id!r} not found"}

        # Capture fields up front; the row is detached after the session closes.
        row_enterprise_id = row.enterprise_id
        row_job_id = row.job_id
        row_source_ref = row.source_ref
        row_source_type = row.source_type
        row_bronze_path = row.s3_bronze_path

    # --- Enterprise scoping -------------------------------------------------
    if row_enterprise_id is not None and row_enterprise_id != enterprise_id:
        return {
            "error": (
                f"source_id {source_id!r} belongs to a different enterprise"
            )
        }

    # --- Run scoping --------------------------------------------------------
    if job_id is None or row_job_id != job_id:
        return {
            "error": (
                f"source_id {source_id!r} was not fetched in the current run "
                "(only sources fetched in this run can be cited)"
            )
        }

    if not row_bronze_path:
        return {"error": f"source_id {source_id!r} has no bronze content stored"}

    # Lazy import to break the circular chain
    # (services.agent → langgraph_service → reporting_agent → research_agent
    # → tools.cite_source → services.ingestion.store).
    from backend.services.agent.workspace import workspace_prefix

    # --- Compute keys -------------------------------------------------------
    storage = get_storage()
    bronze_key = _bronze_content_key(row_bronze_path, row_source_type)
    filename = _derive_citation_filename(source_id, row_source_ref, row_source_type)
    dest_key = (
        f"{workspace_prefix(enterprise_id, thread_id)}/research/citations/{filename}"
    )
    virtual_path = f"/research/citations/{filename}"

    # --- Idempotency check --------------------------------------------------
    if storage.exists(dest_key):
        try:
            size_bytes = sum(
                obj["size"] for obj in storage.list_objects(dest_key)
            )
        except Exception:  # noqa: BLE001 — listing failure shouldn't block return
            size_bytes = 0
        return {
            "path": virtual_path,
            "size_bytes": size_bytes,
            "source_ref": row_source_ref,
            "source_type": row_source_type,
            "already_existed": True,
        }

    # --- Copy bytes ---------------------------------------------------------
    if not storage.exists(bronze_key):
        return {
            "error": (
                f"bronze content for source_id {source_id!r} not found at "
                f"{bronze_key!r}"
            )
        }
    content = storage.read(bronze_key)
    storage.write(dest_key, content)
    logger.info(
        "cite_source: copied %s (%d bytes) → %s",
        source_id, len(content), dest_key,
    )
    return {
        "path": virtual_path,
        "size_bytes": len(content),
        "source_ref": row_source_ref,
        "source_type": row_source_type,
        "already_existed": False,
    }
