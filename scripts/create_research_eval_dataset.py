"""Create (or verify) the LangSmith dataset for Research Agent evaluation.

Creates a single-example dataset named ``research-agent-eval`` in LangSmith.
Safe to run multiple times — skips silently if the dataset already exists.

Dataset layout
--------------
  inputs:  {"task": "<research prompt>"}
  outputs: {"reference_urls": [...], "pass_threshold": <int>}

The test (``tests/evaluation/agents/research_agent/test_research_agent.py``)
reads ``reference_urls`` and ``pass_threshold`` from the stored example so
that gold-standard sources and scoring thresholds can be updated here without
touching test code.

Usage
-----
    uv run python scripts/create_research_eval_dataset.py

Requires
--------
    LANGCHAIN_API_KEY (or LANGSMITH_API_KEY) set in ``.env`` or environment.
"""

from __future__ import annotations

from dotenv import load_dotenv
from langsmith import Client

load_dotenv()

# ---------------------------------------------------------------------------
# Dataset definition
# ---------------------------------------------------------------------------

DATASET_NAME = "research-agent-eval"

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

REFERENCE_ANSWER = (
    "Samarth Diamond (est. 1987, Mumbai) manufactures small-size round brilliant-cut "
    "diamonds (1.00-3.00mm). An RJC member since April 2019, it holds COP certification "
    "#0000 6513 (October 2025 - October 2028) and is a De Beers Sightholder that has "
    "passed the De Beers BPP compliance audit. The company aligns with the Watch and "
    "Jewellery Initiative 2030 (WJI2030). Samarth sources 70-75% of rough diamonds from "
    "De Beers, with the balance from South Africa, Canada, and Namibia. Its proprietary "
    "'Mines to Market' traceability software tracks each stone to its Kimberley Process "
    "number and origin. A 1.5 MW solar plant and windmill supply 85% of electricity at "
    "the Gujarat facility. The campus has 22,000 planted trees and recharges ~25 million "
    "liters of rainwater annually. The company targets carbon neutrality by 2030. CSR "
    "includes adoption of Navdeep Vidhya Mandir school (~450 students) in North Gujarat "
    "and Rs. 1,00,000 employee medical coverage. Samarth has published sustainability "
    "reports — the latest (2025) themed 'Crafting Brilliance, Spreading Happiness' — "
    "structured around four pillars: Planet, Product, People, and Process."
)



# ---------------------------------------------------------------------------
# Script
# ---------------------------------------------------------------------------

def main() -> None:
    """Create the LangSmith dataset if it does not already exist.

    Checks for an existing dataset by name before creating to make the script
    idempotent. Prints the dataset ID on creation or skips with a message.

    Raises:
        langsmith.LangSmithError: If the API key is missing or the request fails.
    """
    client = Client()

    # --- Check for existing dataset -----------------------------------------
    existing = list(client.list_datasets(dataset_name=DATASET_NAME))
    if existing:
        print(f"Dataset '{DATASET_NAME}' already exists ({existing[0].id}) — skipping.")
        return

    # --- Create dataset + single example ------------------------------------
    dataset = client.create_dataset(
        dataset_name=DATASET_NAME,
        description=(
            "ESG research agent evaluation — Samarth Diamonds case study. "
            "Tests source coverage quality via LLM judge scoring."
        ),
    )
    client.create_examples(
        dataset_id=dataset.id,
        examples=[
            {
                "inputs": {"task": RESEARCH_INPUT},
                "outputs": {
                    "reference_urls": REFERENCE_URLS,
                    "reference_answer": REFERENCE_ANSWER,
                },
            }
        ],
    )
    print(f"Created dataset '{DATASET_NAME}' ({dataset.id}) with 1 example.")


if __name__ == "__main__":
    main()
