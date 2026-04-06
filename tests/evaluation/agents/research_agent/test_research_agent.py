"""Evaluation test: Research Agent source coverage.

Runs the Research Agent against a fixed ESG research objective, mocks all
DB/storage side-effects, and scores the agent's fetched sources against a
curated reference set using Claude Sonnet 4.6 as an LLM judge.

Usage:
    uv run pytest tests/evaluation/agents/research_agent/ -v -s

Requires:
    ANTHROPIC_API_KEY and SERPER_API_KEY in .env
    No Docker containers needed — storage and DB are fully mocked.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import anthropic
import pytest

from backend.ai.agents.research_agent import build_research_graph

# ---------------------------------------------------------------------------
# Test input and reference set
# ---------------------------------------------------------------------------

RESEARCH_INPUT = (
    "Research the ESG performance and sustainability practices of Samarth Diamonds."
)

# Gold-standard sources a thorough ESG researcher should find.
# The LLM judge evaluates thematic coverage, not exact URL matches —
# a different year's report or an equivalent page counts as a valid hit.
REFERENCE_URLS = [
    "https://samarthdiamond.com/sustainability/",
    "https://samarthdiamond.com/wp-content/uploads/2026/03/Samarth%20Diamond%20-%20Sustainability%20Report%202025%20.pdf",
    "https://www.responsiblejewellery.com/member/samarth-diamond/",
    "https://samarthdiamond.com/category/csr/",
    "https://samarthdiamonds.com/ethical-sourcing-of-natural-diamonds/",
]

PASS_THRESHOLD = 6  # score out of 10; fail the test if below this


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_source(url: str, ext: str = "") -> dict:
    """Build a fake ingestion_service store result for a given URL.

    Args:
        url: The fetched URL, stored as source_ref.
        ext: File extension for binary files (e.g. "pdf"). Empty = web page.

    Returns:
        Dict shaped like the real store_page / store_binary return value.
    """
    source_type = f"web_{ext}" if ext else "web_page"
    return {
        "source_id": str(uuid.uuid4()),
        "s3_bronze_path": f"enterprise/test/bronze/{uuid.uuid4()}/",
        "source_type": source_type,
        "preview": f"[mock] {url[:120]}",
    }


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
# Test
# ---------------------------------------------------------------------------

class TestResearchAgentEvaluation:
    """LLM-judged evaluation of the Research Agent's source coverage."""

    @pytest.mark.asyncio
    async def test_source_coverage_samarth_diamonds(self):
        """Run the agent on a Samarth Diamonds ESG objective and score its fetched sources.

        Storage and DB calls are fully mocked so no infrastructure is needed.
        Real HTTP traffic runs against Serper (web_search) and crawl4ai (web_fetch).

        The mock layer is coordinated:
          1. ``record_search_query`` assigns result_ids and stores url→id mappings.
          2. ``get_search_result`` resolves those ids back to URLs for web_fetch.
          3. ``store_page`` / ``store_binary`` capture URLs as the agent fetches them.

        Final score is computed by an LLM judge. Fails if score < PASS_THRESHOLD.
        """
        fetched_urls: list[str] = []

        # In-process registry so get_search_result can resolve result_ids
        # assigned by mock_record_search_query without touching the DB.
        _result_registry: dict[str, str] = {}  # result_id → url

        async def mock_record_search_query(
            job_id: str, search_query_text: str, results: list[dict]
        ) -> tuple[str, list[dict]]:
            query_id = str(uuid.uuid4())
            enriched = [
                {**r, "result_id": str(uuid.uuid4()), "position": r.get("position", i + 1)}
                for i, r in enumerate(results)
            ]
            for r in enriched:
                _result_registry[r["result_id"]] = r["url"]
            return query_id, enriched

        async def mock_get_search_result(result_id: str) -> dict | None:
            url = _result_registry.get(result_id)
            if url is None:
                return None
            return {"url": url, "title": "", "snippet": "", "query_id": None}

        async def mock_store_page(*, url: str, **kwargs) -> dict:
            fetched_urls.append(url)
            return _fake_source(url)

        async def mock_store_binary(*, url: str, **kwargs) -> dict:
            ext = url.rsplit(".", 1)[-1].lower() if "." in url else "bin"
            fetched_urls.append(url)
            return _fake_source(url, ext)

        with (
            patch(
                "backend.services.ingestion_service.record_search_query",
                side_effect=mock_record_search_query,
            ),
            patch(
                "backend.services.ingestion_service.get_search_result",
                side_effect=mock_get_search_result,
            ),
            patch(
                "backend.services.ingestion_service.check_duplicate",
                AsyncMock(return_value=None),
            ),
            patch(
                "backend.services.ingestion_service.store_page",
                side_effect=mock_store_page,
            ),
            patch(
                "backend.services.ingestion_service.store_binary",
                side_effect=mock_store_binary,
            ),
        ):
            graph = build_research_graph()
            config = {
                "configurable": {
                    "thread_id": str(uuid.uuid4()),  # fresh per run — avoids StateBackend restoring old state
                    "enterprise_id": "test-enterprise",
                    "job_id": str(uuid.uuid4()),
                }
            }
            await graph.ainvoke(
                {"messages": [{"role": "user", "content": RESEARCH_INPUT}]},
                config=config,
            )

        # --- Score with LLM judge --------------------------------------------
        score, reasoning = _llm_judge(fetched_urls, REFERENCE_URLS)

        print(f"\n{'=' * 60}")
        print(f"Fetched {len(fetched_urls)} URL(s):")
        for u in fetched_urls:
            print(f"  {u}")
        print(f"\nLLM Judge score: {score}/10")
        print(f"Reasoning: {reasoning}")
        print("=" * 60)

        assert score >= PASS_THRESHOLD, (
            f"Coverage score {score}/10 is below threshold {PASS_THRESHOLD}/10.\n"
            f"Reasoning: {reasoning}\n"
            f"Fetched {len(fetched_urls)} URL(s):\n"
            + "\n".join(f"  {u}" for u in fetched_urls)
        )