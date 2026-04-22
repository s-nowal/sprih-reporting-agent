"""Evaluation test: Research Agent — source coverage and answer quality.

Runs the Research Agent against LangSmith datasets, verifies the full DB
provenance chain and S3 storage layout, then scores source coverage and
answer quality with LLM judges.

Usage:
    uv run pytest tests/evaluation/agents/research_agent/ -v -s

Requires:
    Docker containers running: docker compose up -d
    ANTHROPIC_API_KEY, SERPER_API_KEY, and LANGCHAIN_API_KEY in .env
    LangSmith datasets created:
        uv run python scripts/create_research_eval_dataset.py
        uv run python scripts/create_research_eval_dataset_10.py
"""

from __future__ import annotations

import json
import uuid

import anthropic

from backend.ai.agents.research_agent import build_research_graph
from backend.infra.registry import get_db
from backend.models.job import Job

from tests.evaluation.harness import EvalConfig, make_score_evaluator, run_eval
from tests.evaluation.verifiers.db_provenance import verify_provenance_chain
from tests.evaluation.verifiers.storage import verify_source_files

ENTERPRISE_ID = "test-enterprise"


# ---------------------------------------------------------------------------
# LLM judge (agent-specific: knows what to score and how)
# ---------------------------------------------------------------------------

def _coverage_judge(run_output: dict, reference_output: dict) -> tuple[float, str]:
    """Score source coverage using Claude Sonnet 4.6.

    Sends fetched and reference URLs to the LLM and asks for a 0–10 coverage
    score with a one-sentence rationale. A different year's report or an
    equivalent page on the same domain counts as a valid match.

    Args:
        run_output: Target function outputs — must contain "fetched_urls" (list[str]).
        reference_output: Dataset example outputs — must contain "reference_urls" (list[str]).

    Returns:
        Tuple of (score 0–10, one-sentence reasoning).
    """
    fetched_urls = run_output.get("fetched_urls", [])
    reference_urls = reference_output.get("reference_urls", [])

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

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    result = json.loads(message.content[0].text)
    return float(result["score"]), result["reasoning"]


_coverage_evaluator = make_score_evaluator(
    _coverage_judge,
    score_key="source_coverage",
    name="research_agent_coverage_evaluator",
)


def _answer_judge(run_output: dict, reference_output: dict) -> tuple[float, str]:
    """Score answer quality using Claude Sonnet 4.6.

    Compares the agent's research output against a reference answer for
    overall topical alignment. This is a loose check — the agent does not
    need to reproduce the reference verbatim, just cover the same major
    themes and key facts.

    Args:
        run_output: Target function outputs — must contain "agent_output" (str).
        reference_output: Dataset example outputs — must contain "reference_answer" (str).

    Returns:
        Tuple of (score 0–10, one-sentence reasoning).
    """
    agent_output = run_output.get("agent_output", "")
    reference_answer = reference_output.get("reference_answer", "")

    if not reference_answer:
        return 5.0, "No reference answer provided — default score."

    agent_block = agent_output[:4000] if agent_output else "(no output)"

    prompt = f"""\
You are evaluating an ESG research agent's answer quality.

REFERENCE ANSWER (gold standard — the key themes and facts a good answer should cover):
{reference_answer}

AGENT OUTPUT:
{agent_block}

Score the agent's answer from 0 to 10 based on overall topical coverage:
  10 — Covers all major themes from the reference and adds useful detail
  7–9 — Covers most major themes, minor omissions
  4–6 — Covers some themes but misses important ones
  1–3 — Mostly off-topic or superficial
  0  — No relevant content

This is a loose thematic check. The agent does NOT need to match the reference
word-for-word. Different phrasing, additional context, or newer data are fine
as long as the same key topics are addressed.

Respond with JSON only: {{"score": <int 0-10>, "reasoning": "<one sentence>"}}"""

    client = anthropic.Anthropic()
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}],
    )
    result = json.loads(message.content[0].text)
    return float(result["score"]), result["reasoning"]


_answer_evaluator = make_score_evaluator(
    _answer_judge,
    score_key="answer_quality",
    name="research_agent_answer_evaluator",
)

# ---------------------------------------------------------------------------
# Eval config
# ---------------------------------------------------------------------------

EVAL_CONFIG = EvalConfig(
    dataset_name="research-agent-eval",
    experiment_prefix="research-agent",
    pass_threshold=6,
    evaluators=[_coverage_evaluator, _answer_evaluator],
)

EVAL_CONFIG_10 = EvalConfig(
    dataset_name="research-agent-eval-10",
    experiment_prefix="research-agent-10",
    pass_threshold=5,
    evaluators=[_coverage_evaluator, _answer_evaluator],
)


# ---------------------------------------------------------------------------
# Target function
# ---------------------------------------------------------------------------

async def _run_research_agent(inputs: dict) -> dict:
    """Run the Research Agent end-to-end and verify all stored artefacts.

    Creates a real job row, invokes the agent against live infrastructure,
    then delegates DB provenance and S3 storage verification to the shared
    verifiers. Raises AssertionError on any failure so LangSmith marks the
    run as errored.

    Args:
        inputs: Dataset example inputs — must contain "task" (str).

    Returns:
        Dict with "fetched_urls" (list[str]), "sources" (list of dicts
        with id, source_ref, source_type, s3_bronze_path), and
        "agent_output" (str) — the agent's final research message.

    Raises:
        AssertionError: If any DB or storage integrity check fails.
    """
    task = inputs["task"]
    job_id = str(uuid.uuid4())
    thread_id = str(uuid.uuid4())

    # --- Create job row so search_queries / data_sources FKs resolve ---------
    db = get_db()
    async with db() as session:
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
    result = await graph.ainvoke(
        {"messages": [{"role": "user", "content": task}]},
        config={
            "configurable": {
                "thread_id": thread_id,
                "enterprise_id": ENTERPRISE_ID,
                "job_id": job_id,
            }
        },
    )

    # --- Extract the agent's final research output ----------------------------
    messages = result.get("messages", [])
    agent_output = ""
    for msg in reversed(messages):
        content = getattr(msg, "content", "")
        if content and getattr(msg, "type", "") == "ai":
            agent_output = content
            break

    # --- Verify DB provenance chain and storage layout -----------------------
    provenance = await verify_provenance_chain(job_id)
    for src in provenance.sources:
        verify_source_files(src)

    return {
        "fetched_urls": [s["source_ref"] for s in provenance.sources],
        "sources": provenance.sources,
        "agent_output": agent_output,
    }


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

async def test_research_agent_eval():
    """Full evaluation: dataset → agent run → storage verification → LLM scoring.

    Runs the agent against the LangSmith dataset, verifies DB and storage
    integrity inside the target function, then asserts coverage meets the
    pass threshold.
    """
    result = await run_eval(_run_research_agent, EVAL_CONFIG)
    assert result.passed, (
        f"Coverage avg={result.avg_score:.1f} < threshold={EVAL_CONFIG.pass_threshold} "
        f"(experiment: {result.experiment_name})"
    )


async def test_research_agent_eval_10():
    """Broad evaluation: 10 diverse ESG research tasks across industries.

    Runs the same agent and verifiers as test_research_agent_eval but against
    a 10-example dataset covering different companies, industries, and query
    types (general ESG, framework compliance, climate, peer comparison, supply
    chain, controversy, governance, sector environmental, investment ESG, and
    social impact). Uses a lower pass threshold to account for variance across
    diverse tasks.

    Requires:
        LangSmith dataset created: uv run python scripts/create_research_eval_dataset_10.py
    """
    result = await run_eval(_run_research_agent, EVAL_CONFIG_10)
    assert result.passed, (
        f"Coverage avg={result.avg_score:.1f} < threshold={EVAL_CONFIG_10.pass_threshold} "
        f"(experiment: {result.experiment_name})"
    )
