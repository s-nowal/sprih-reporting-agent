"""Retry failed examples from a partially-complete evaluation experiment.

Identifies examples that errored or never ran in a given LangSmith experiment,
prints them with indexes, and reruns a chosen subset — appending scores to the
original experiment rather than creating a new one.

Usage:
    # Retry ALL failed examples automatically:
    uv run python scripts/retry_failed_eval.py <experiment_name>

    # Inspect first, then choose which to retry (interactive):
    uv run python scripts/retry_failed_eval.py <experiment_name> --select

Example:
    uv run python scripts/retry_failed_eval.py research-agent-10-979a8b26
    uv run python scripts/retry_failed_eval.py research-agent-10-979a8b26 --select
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Allow running from repo root without installing the package
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv

load_dotenv()

# Import must happen after load_dotenv so env vars are available
from tests.evaluation.agents.research_agent.test_research_agent import (  # noqa: E402
    EVAL_CONFIG_10,
    _run_research_agent,
)
from tests.evaluation.harness import get_failed_examples, retry_failed_runs  # noqa: E402

# Map experiment prefixes → configs. Add new agents here as they are built.
_CONFIGS = {
    "research-agent-10": EVAL_CONFIG_10,
}


def _resolve_config(experiment_name: str):
    """Pick the EvalConfig matching the experiment prefix."""
    for prefix, config in _CONFIGS.items():
        if experiment_name.startswith(prefix):
            return config
    # Fallback: list known prefixes and exit
    known = ", ".join(f"'{p}'" for p in _CONFIGS)
    print(
        f"ERROR: Cannot infer config for experiment '{experiment_name}'.\n"
        f"Known prefixes: {known}\n"
        "Add the experiment to _CONFIGS in this script if needed."
    )
    sys.exit(1)


async def main(experiment_name: str, select: bool) -> None:
    """Identify and retry failed examples in the given experiment.

    Args:
        experiment_name: Exact LangSmith experiment name (e.g. "research-agent-10-979a8b26").
        select: If True, prompt the user to choose which failed examples to retry.
            If False, retry all failed examples automatically.
    """
    config = _resolve_config(experiment_name)

    failed = get_failed_examples(experiment_name, config)
    if not failed:
        return

    examples_to_retry = failed

    if select:
        raw = input(
            "\nEnter indexes to retry (comma-separated, e.g. '0,2'), "
            "or press Enter to retry all: "
        ).strip()
        if raw:
            try:
                indexes = [int(x.strip()) for x in raw.split(",")]
                examples_to_retry = [failed[i] for i in indexes]
            except (ValueError, IndexError) as e:
                print(f"Invalid selection: {e}")
                sys.exit(1)

    print(f"\nRetrying {len(examples_to_retry)} example(s)...")
    result = await retry_failed_runs(
        examples_to_retry, experiment_name, config, _run_research_agent
    )
    print(
        f"\nDone — avg_score={result.avg_score:.1f}, passed={result.passed}\n"
        f"Results appended to experiment: {result.experiment_name}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("experiment_name", help="LangSmith experiment name to resume")
    parser.add_argument(
        "--select",
        action="store_true",
        help="Prompt to choose which failed examples to retry (default: retry all)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.experiment_name, args.select))
