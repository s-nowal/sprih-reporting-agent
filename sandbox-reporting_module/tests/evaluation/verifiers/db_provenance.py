"""DB provenance chain verifier for evaluation tests.

Asserts that the four-table provenance chain is intact after an agent run:
  jobs → search_queries → search_results → data_sources

Usage:
    provenance = await verify_provenance_chain(job_id)
    # provenance.sources is a list of {id, source_ref, source_type, s3_bronze_path}
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from backend.infra.registry import get_session_factory
from backend.models.data_source import DataSource
from backend.models.search_query import SearchQuery
from backend.models.search_result import SearchResult

_KNOWN_SOURCE_TYPES = {"web_page", "web_pdf", "web_xlsx", "web_csv", "web_docx", "web_doc"}


@dataclass
class ProvenanceResult:
    """Result of a provenance chain verification.

    Attributes:
        query_ids: IDs of all SearchQuery rows found for the job.
        result_ids: IDs of all SearchResult rows linked to those queries.
        sources: List of dicts with keys id, source_ref, source_type, s3_bronze_path
            for each DataSource row linked to the job.
    """

    query_ids: set[str]
    result_ids: set[str]
    sources: list[dict]


async def verify_provenance_chain(job_id: str) -> ProvenanceResult:
    """Verify the DB provenance chain for a completed agent job.

    Runs three SELECT queries in a single session to assert:
    - ≥1 search_queries row for job_id, each with non-empty query_text and
      results_count ≥ 0; at least one query returned results_count > 0
    - ≥1 search_results rows linked to those query_ids, each with a URL and
      position ≥ 1
    - ≥1 data_sources rows for job_id, each with s3_bronze_path, source_ref,
      known source_type, status == 'fetched', fetched_at set, and
      search_result_id tracing back to this job's search_results

    Args:
        job_id: UUID of the job row to verify (must already exist in DB).

    Returns:
        ProvenanceResult containing query_ids, result_ids, and a sources list
        ready to pass to verify_source_files().

    Raises:
        AssertionError: On any chain violation, with a message describing
            the specific failure and the job_id.
    """
    session_factory = get_session_factory()

    async with session_factory() as session:

        # --- search_queries --------------------------------------------------
        sq_rows = (
            await session.execute(
                select(SearchQuery).where(SearchQuery.job_id == job_id)
            )
        ).scalars().all()

        assert sq_rows, f"No search_queries rows for job_id={job_id} — agent made no web_search calls"
        for q in sq_rows:
            assert q.query_text.strip(), f"search_query {q.id}: empty query_text"
            assert q.results_count >= 0, f"search_query {q.id}: results_count is negative"
        assert any(q.results_count > 0 for q in sq_rows), (
            f"All search queries for job_id={job_id} returned 0 results — Serper may be failing"
        )

        query_ids = {q.id for q in sq_rows}

        # --- search_results --------------------------------------------------
        sr_rows = (
            await session.execute(
                select(SearchResult).where(SearchResult.query_id.in_(query_ids))
            )
        ).scalars().all()

        assert sr_rows, f"No search_results rows for job_id={job_id} — FK or insert bug in record_search_query"
        for r in sr_rows:
            assert r.url, f"search_result {r.id}: missing url"
            assert r.query_id in query_ids, (
                f"search_result {r.id}: query_id {r.query_id!r} not in this job's queries"
            )
            assert r.position >= 1, f"search_result {r.id}: position={r.position}"

        result_ids = {r.id for r in sr_rows}

        # --- data_sources ----------------------------------------------------
        ds_rows = (
            await session.execute(
                select(DataSource).where(DataSource.job_id == job_id)
            )
        ).scalars().all()

        assert ds_rows, f"No data_sources rows for job_id={job_id} — agent fetched nothing"
        for ds in ds_rows:
            assert ds.s3_bronze_path, f"data_source {ds.id}: s3_bronze_path is None"
            assert ds.source_ref, f"data_source {ds.id}: source_ref (URL) is None"
            assert ds.source_type in _KNOWN_SOURCE_TYPES, (
                f"data_source {ds.id}: unexpected source_type={ds.source_type!r}"
            )
            assert ds.status == "fetched", (
                f"data_source {ds.id}: status={ds.status!r} (expected 'fetched')"
            )
            assert ds.fetched_at is not None, f"data_source {ds.id}: fetched_at is None"
            assert ds.search_result_id in result_ids, (
                f"data_source {ds.id}: search_result_id={ds.search_result_id!r} "
                "not in this job's search_results (broken provenance chain)"
            )

        sources = [
            {
                "id": ds.id,
                "source_ref": ds.source_ref,
                "source_type": ds.source_type,
                "s3_bronze_path": ds.s3_bronze_path,
            }
            for ds in ds_rows
        ]

    return ProvenanceResult(
        query_ids=query_ids,
        result_ids=result_ids,
        sources=sources,
    )
