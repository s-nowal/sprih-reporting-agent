"""Evaluation test: Research Agent — storage integrity + source coverage.

Runs the Research Agent end-to-end against real infrastructure and verifies
every layer of what should be stored after a run:

  DB TABLES (MariaDB)
  ├── jobs            — 1 row (created by test before agent starts)
  ├── search_queries  — 1 row per web_search call (query text + result count)
  ├── search_results  — N rows per query (URL, title, snippet, position)
  └── data_sources    — 1 row per web_fetch call (URL, type, S3 path, status)

  S3 / LOCAL STORAGE  (data/s3/public/bronze/{source_id}/)
  ├── web_page sources
  │   ├── content.md     — full crawled markdown (non-empty)
  │   └── meta.json      — {source_ref, source_type, content_length, crawled_at}
  └── web_pdf sources
      ├── original.pdf   — raw downloaded binary
      ├── content.md     — pymupdf extracted text with ## Page N headers (non-empty)
      ├── meta.json      — {source_ref, source_type, pages, images, …}
      └── images/        — embedded PDF images (page_{n}_img_{i}.{ext})

  PROVENANCE CHAIN
  job → search_queries → search_results → data_sources
  Every data_source must trace back to a search_result in the same job.

The test case lives in the LangSmith dataset ``research-agent-eval`` (created
by ``scripts/create_research_eval_dataset.py``).  Reference URLs and the pass
threshold are stored in the dataset's ``outputs`` so they can be updated
without touching this file.

Usage:
    uv run pytest tests/evaluation/agents/research_agent/ -v -s

Requires:
    Docker containers running: docker compose up -d
    ANTHROPIC_API_KEY, SERPER_API_KEY, and LANGCHAIN_API_KEY in .env
    LangSmith dataset created: uv run python scripts/create_research_eval_dataset.py
"""

from __future__ import annotations

import json
import uuid

import anthropic
import pytest
from langsmith import aevaluate
from langsmith.evaluation import EvaluationResult
from sqlalchemy import select

from backend.ai.agents.research_agent import build_research_graph
from backend.infra.registry import get_session_factory, get_storage
from backend.models.data_source import DataSource
from backend.models.job import Job
from backend.models.search_query import SearchQuery
from backend.models.search_result import SearchResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ENTERPRISE_ID = "test-enterprise"
DATASET_NAME = "research-agent-eval"
PASS_THRESHOLD = 6  # minimum coverage score out of 10 to pass

_KNOWN_SOURCE_TYPES = {"web_page", "web_pdf", "web_xlsx", "web_csv", "web_docx", "web_doc"}


# ---------------------------------------------------------------------------
# LLM judge
# ---------------------------------------------------------------------------

def _llm_judge(fetched_urls: list[str], reference_urls: list[str]) -> tuple[int, str]:
    """Score source coverage using Claude Sonnet 4.6.

    Sends fetched and reference URLs to the LLM and asks for a 0–10
    coverage score with a one-sentence rationale.

    Args:
        fetched_urls: URLs the agent actually fetched and stored.
        reference_urls: Gold-standard URLs a thorough ESG researcher should find.

    Returns:
        Tuple of ``(score, reasoning)`` where score is 0–10.
    """
    client = anthropic.Anthropic()

    fetched_block = (
        "\n".join(f"  - {u}" for u in fetched_urls)
        if fetched_urls
        else "  (none fetched)"
    )
    reference_block = "\n".join(f"  - {u}" for u in reference_urls)

    prompt = f"""\
You are evaluating an ESG research agent's source coverage.

REFERENCE SOURCES (gold standard — what a thorough ESG researcher should find):
{reference_block}

AGENT FETCHED SOURCES:
{fetched_block}

Score the agent's coverage from 0 to 10:
  10 — Found all reference sources or direct equivalents
  7–9 — Found most primary sources, minor gaps
  4–6 — Found some relevant sources but missed important ones
  1–3 — Mostly low-quality or irrelevant sources
  0  — No relevant sources found

A different year's ESG/annual report, or an equivalent page on the same domain,
counts as a valid match for the corresponding reference URL.

Respond with JSON only: {{"score": <int 0-10>, "reasoning": "<one sentence>"}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    result = json.loads(message.content[0].text)
    return int(result["score"]), result["reasoning"]


# ---------------------------------------------------------------------------
# LangSmith evaluator
# ---------------------------------------------------------------------------

def _coverage_evaluator(
    inputs: dict,
    outputs: dict,
    reference_outputs: dict,
) -> EvaluationResult:
    """LangSmith evaluator: score source coverage via LLM judge.

    Wraps ``_llm_judge`` and maps its result to a LangSmith
    ``EvaluationResult`` so the score is tracked per experiment.

    Args:
        inputs: Dataset example inputs (unused — agent already ran).
        outputs: Target function outputs: ``{"fetched_urls": [...], "sources": [...]}``.
        reference_outputs: Dataset example outputs:
            ``{"reference_urls": [...], "pass_threshold": int}``.

    Returns:
        ``EvaluationResult`` with ``key="source_coverage"``, ``score`` 0–10,
        and ``comment`` containing the LLM judge's one-sentence reasoning.
    """
    fetched_urls = outputs.get("fetched_urls", [])
    reference_urls = reference_outputs.get("reference_urls", [])
    score, reasoning = _llm_judge(fetched_urls, reference_urls)
    return EvaluationResult(
        key="source_coverage",
        score=score,
        value={"fetched_count": len(fetched_urls)},
        comment=reasoning,
    )


# ---------------------------------------------------------------------------
# Target function (agent run + verification)
# ---------------------------------------------------------------------------

async def _run_research_agent(inputs: dict) -> dict:
    """Run the Research Agent end-to-end and verify all stored artefacts.

    Creates a real job row, invokes the agent, then asserts the full
    DB provenance chain and S3 storage layout are correct.  Raises
    ``AssertionError`` on any verification failure — LangSmith marks the
    run as errored so it surfaces in the experiment dashboard.

    Args:
        inputs: Dataset example inputs — must contain ``"task"`` (str).

    Returns:
        dict with ``"fetched_urls"`` (list[str]) and ``"sources"``
        (list of dicts with id, source_ref, source_type, s3_bronze_path).

    Raises:
        AssertionError: If any DB or storage integrity check fails.
    """
    task = inputs["task"]
    job_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())
    session_factory = get_session_factory()

    # --- Create job row so search_queries / data_sources FKs resolve ---------
    async with session_factory() as session:
        session.add(Job(
            id=job_id,
            enterprise_id=ENTERPRISE_ID,
            thread_id=thread_id,
            job_type="research",
            status="running",
        ))
        await session.commit()

    # --- Run the research agent ----------------------------------------------
    graph = build_research_graph()
    config = {
        "configurable": {
            "thread_id": thread_id,
            "enterprise_id": ENTERPRISE_ID,
            "job_id": job_id,
        }
    }
    await graph.ainvoke(
        {"messages": [{"role": "user", "content": task}]},
        config=config,
    )

    # ========================================================================
    # VERIFICATION 1 — DB provenance chain
    # Expected:
    #   search_queries : ≥1 row linked to job_id
    #   search_results : ≥1 row per query (linked via query_id)
    #   data_sources   : ≥1 row linked to job_id (linked via search_result_id)
    # ========================================================================

    async with session_factory() as session:

        # --- search_queries --------------------------------------------------
        sq_rows = (
            await session.execute(
                select(SearchQuery).where(SearchQuery.job_id == job_id)
            )
        ).scalars().all()
        assert sq_rows, "No search_queries rows found — agent made no web_search calls"
        for q in sq_rows:
            assert q.query_text.strip(), f"search_query {q.id}: empty query_text"
            assert q.results_count >= 0, f"search_query {q.id}: results_count is negative"
        assert any(q.results_count > 0 for q in sq_rows), (
            "All search queries returned 0 results — Serper may be failing"
        )

        query_ids = {q.id for q in sq_rows}

        # --- search_results --------------------------------------------------
        sr_rows = (
            await session.execute(
                select(SearchResult).where(SearchResult.query_id.in_(query_ids))
            )
        ).scalars().all()
        assert sr_rows, "No search_results rows — FK or insert bug in record_search_query"
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
        assert ds_rows, "No data_sources rows — agent fetched nothing"
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
                "is not in this job's search_results (broken provenance chain)"
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

    # ========================================================================
    # VERIFICATION 2 — S3 / LocalStorage files
    # Expected layout per source_id:
    #   web_page → content.md  (non-empty markdown), meta.json
    #   web_pdf  → original.pdf, content.md (extracted text), meta.json
    #              + images/ (may be empty if PDF has no embedded images)
    # ========================================================================

    storage = get_storage()

    for src in sources:
        base = src["s3_bronze_path"]   # "public/bronze/{sid}/"
        stype = src["source_type"]
        sid = src["id"]
        url = src["source_ref"]

        # meta.json — required for all source types
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

    return {
        "fetched_urls": [s["source_ref"] for s in sources],
        "sources": sources,
    }


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

class TestResearchAgentEvaluation:
    """End-to-end evaluation of the Research Agent via LangSmith dataset.

    Pulls the test case (task prompt + reference URLs + pass threshold) from
    the ``research-agent-eval`` LangSmith dataset, runs the agent, verifies
    storage integrity, and scores source coverage with an LLM judge.

    Each test run is logged as a LangSmith experiment so coverage trends are
    trackable across code changes.
    """

    @pytest.mark.asyncio
    async def test_source_coverage_samarth_diamonds(self):
        """Full evaluation: dataset → agent run → storage verification → LLM scoring.

        Fetches the single example from the LangSmith dataset, runs the agent
        end-to-end (with DB + S3 verification in the target function), then
        asserts the coverage score meets the dataset-specified threshold.
        """
        # --- Run evaluation against LangSmith dataset ------------------------
        results = await aevaluate(
            _run_research_agent,
            data=DATASET_NAME,
            evaluators=[_coverage_evaluator],
            experiment_prefix="research-agent",
        )

        # --- Assert every example passed -------------------------------------
        async for result in results:
            run = result["run"]
            example = result["example"]
            eval_results = result["evaluation_results"]["results"]

            # Target function must not have raised
            assert run.error is None, f"Agent run raised an error:\n{run.error}"

            outputs = run.outputs or {}
            sources = outputs.get("sources", [])
            fetched_urls = outputs.get("fetched_urls", [])

            coverage = next(r for r in eval_results if r.key == "source_coverage")

            # --- Print run summary -------------------------------------------
            print(f"\n{'=' * 60}")
            print(
                f"DB: {len(sources)} fetched source(s)"
            )
            print("Sources fetched:")
            for s in sources:
                print(f"  [{s['source_type']}] {s['source_ref']}")
            print(f"\nLLM Judge score: {coverage.score}/10")
            print(f"Reasoning: {coverage.comment}")
            print("=" * 60)

            assert coverage.score >= PASS_THRESHOLD, (
                f"Coverage score {coverage.score}/10 is below threshold "
                f"{PASS_THRESHOLD}/10.\n"
                f"Reasoning: {coverage.comment}\n"
                f"Fetched {len(fetched_urls)} URL(s):\n"
                + "\n".join(
                    f"  [{s['source_type']}] {s['source_ref']}" for s in sources
                )
            )
