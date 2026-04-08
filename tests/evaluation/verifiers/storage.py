"""Storage layout verifier for evaluation tests.

Asserts that the expected files exist and are well-formed for a single
data source after an agent run.

Usage:
    for src in provenance.sources:
        verify_source_files(src)
"""

from __future__ import annotations

import json

from backend.infra.registry import get_storage


def verify_source_files(source: dict) -> None:
    """Verify storage files are present and well-formed for one data source.

    Expected layouts:
    - All types: meta.json with matching source_ref/source_type, non-empty crawled_at
    - web_page: content.md (>100 chars), meta.content_length > 0
    - web_pdf: original.pdf, content.md (>100 chars, has '## Page' markers),
               meta.pages (int > 0), meta.images (each path exists in storage)

    Args:
        source: Dict with keys id, source_ref, source_type, s3_bronze_path.
            s3_bronze_path is the relative storage prefix, e.g. "public/bronze/{id}/".

    Raises:
        AssertionError: On any missing file, malformed JSON, or unexpected field value.
            Messages include [source_type] url and the missing path for easy diagnosis.
    """
    storage = get_storage()
    base = source["s3_bronze_path"]
    stype = source["source_type"]
    sid = source["id"]
    url = source["source_ref"]

    # --- meta.json — required for all source types ---------------------------
    assert storage.exists(f"{base}meta.json"), (
        f"[{stype}] {url}\n  Missing: {base}meta.json"
    )
    meta = json.loads(storage.read_text(f"{base}meta.json"))
    assert meta.get("source_ref") == url, (
        f"meta.json source_ref mismatch for source {sid}"
    )
    assert meta.get("source_type") == stype, (
        f"meta.json source_type mismatch for source {sid}"
    )
    assert meta.get("crawled_at"), f"meta.json missing crawled_at for source {sid}"

    # --- source-type-specific files ------------------------------------------
    if stype == "web_page":
        assert storage.exists(f"{base}content.md"), (
            f"[web_page] {url}\n  Missing: {base}content.md"
        )
        content = storage.read_text(f"{base}content.md")
        assert len(content) > 100, (
            f"[web_page] {url}\n  content.md only {len(content)} chars — "
            "crawl likely returned empty or boilerplate-only page"
        )
        assert meta.get("content_length", 0) > 0, (
            f"meta.json content_length=0 for web_page {sid}"
        )

    elif stype == "web_pdf":
        assert storage.exists(f"{base}original.pdf"), (
            f"[web_pdf] {url}\n  Missing: {base}original.pdf"
        )
        assert storage.exists(f"{base}content.md"), (
            f"[web_pdf] {url}\n  Missing: {base}content.md "
            "(pymupdf extraction should have run)"
        )
        extracted = storage.read_text(f"{base}content.md")
        assert len(extracted) > 100, (
            f"[web_pdf] {url}\n  content.md only {len(extracted)} chars"
        )
        assert "## Page" in extracted, (
            f"[web_pdf] {url}\n  content.md missing '## Page N' markers"
        )
        assert "pages" in meta, f"[web_pdf] {url}\n  meta.json missing 'pages' key"
        assert isinstance(meta["pages"], int) and meta["pages"] > 0, (
            f"[web_pdf] {url}\n  meta.json pages={meta['pages']!r}"
        )
        assert "images" in meta, f"[web_pdf] {url}\n  meta.json missing 'images' key"
        for img in meta["images"]:
            assert storage.exists(img["path"]), (
                f"[web_pdf] {url}\n  Declared image missing on disk: {img['path']}"
            )
