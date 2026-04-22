"""Ingestion service — persists crawled content to bronze storage and DB.

Owns the bronze storage pipeline:
- ``store_page``: save web page markdown to bronze + create ``data_sources`` row
- ``store_binary``: save binary file (PDF, XLSX, …) to bronze + create ``data_sources`` row
- ``check_duplicate``: skip re-fetching a URL that has already been stored

Search query provenance (recording queries, resolving result IDs) lives in
``search_service``. This service is agent-agnostic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
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
