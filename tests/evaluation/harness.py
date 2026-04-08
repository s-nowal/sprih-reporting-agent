"""Evaluation harness: reusable LangSmith wiring for evaluation tests.

Provides run_eval() and make_score_evaluator() so individual test files
never import langsmith directly. Swapping to LangFuse means changing only
this file — all evaluators, configs, and test functions stay the same.

Usage:
    from tests.evaluation.harness import EvalConfig, EvalResult, make_score_evaluator, run_eval

    def _my_judge(run_output: dict, reference_output: dict) -> tuple[float, str]:
        ...
        return score, comment

    _my_evaluator = make_score_evaluator(_my_judge, score_key="my_metric")

    EVAL_CONFIG = EvalConfig(
        dataset_name="my-dataset",
        experiment_prefix="my-agent",
        pass_threshold=7,
        evaluators=[_my_evaluator],
    )

    async def test_my_agent():
        result = await run_eval(_run_my_agent, EVAL_CONFIG)
        assert result.passed, f"avg={result.avg_score:.1f} < {EVAL_CONFIG.pass_threshold}"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from langsmith import aevaluate
from langsmith.evaluation import EvaluationResult


@dataclass
class EvalConfig:
    """Configuration for a single evaluation run.

    Attributes:
        dataset_name: LangSmith dataset name to pull examples from.
        experiment_prefix: Prefix for the experiment name in LangSmith.
        pass_threshold: Minimum average score (inclusive) for the test to pass.
        evaluators: List of LangSmith evaluator callables (built via make_score_evaluator).
    """

    dataset_name: str
    experiment_prefix: str
    pass_threshold: float
    evaluators: list[Any] = field(default_factory=list)


@dataclass
class EvalResult:
    """Result of a completed evaluation run.

    Attributes:
        passed: True if avg_score >= EvalConfig.pass_threshold.
        avg_score: Mean score across all examples and evaluators.
        scores: Individual scores collected from all EvaluationResult objects.
        experiment_name: LangSmith experiment name for linking to the UI.
    """

    passed: bool
    avg_score: float
    scores: list[float]
    experiment_name: str


def make_score_evaluator(
    judge_fn: Callable[[dict, dict], tuple[float, str]],
    *,
    score_key: str,
    name: str,
) -> Callable:
    """Wrap a simple judge function into a LangSmith evaluator callable.

    The judge_fn receives plain dicts (run outputs and reference outputs) and
    returns a (score, comment) tuple. This wrapper adapts it to the three-arg
    LangSmith convenience evaluator signature (inputs, outputs, reference_outputs).

    Args:
        judge_fn: Synchronous function with signature
            (run_output: dict, reference_output: dict) -> (float, str).
            run_output is the dict returned by the target function.
            reference_output is the dataset example's outputs dict.
        score_key: Name of the metric as it appears in LangSmith (e.g. "coverage").
        name: Evaluator display name in LangSmith. Convention: "{agent_name}_evaluator"
            (e.g. "research_agent_evaluator").

    Returns:
        A callable compatible with the LangSmith evaluators list.
    """

    def _evaluator(
        inputs: dict,
        outputs: dict,
        reference_outputs: dict,
    ) -> EvaluationResult:
        """LangSmith evaluator: delegates scoring to judge_fn.

        Args:
            inputs: Dataset example inputs (passed through from LangSmith).
            outputs: Target function return value.
            reference_outputs: Dataset example reference outputs.

        Returns:
            EvaluationResult with key=score_key, score, and comment.
        """
        score, comment = judge_fn(outputs, reference_outputs)
        return EvaluationResult(
            key=score_key,
            score=int(score),
            value={"fetched_count": len(outputs.get("fetched_urls", []))},
            comment=comment,
        )

    _evaluator.__name__ = name
    return _evaluator


async def run_eval(
    target_fn: Callable[[dict], Awaitable[dict]],
    config: EvalConfig,
) -> EvalResult:
    """Run a LangSmith evaluation and return a structured result.

    Calls aevaluate() with the target function and config, iterates
    AsyncExperimentResults, collects all non-None scores, and checks
    them against the pass threshold.

    Args:
        target_fn: Async function (inputs: dict) -> dict that runs the agent
            and returns outputs. Must raise AssertionError on verification
            failure so LangSmith marks the run as errored.
        config: EvalConfig describing the dataset, threshold, and evaluators.

    Returns:
        EvalResult with passed, avg_score, scores list, and experiment_name.

    Raises:
        AssertionError: If any target_fn run raised an error (surfaces the
            agent-side exception message).
    """
    results = await aevaluate(
        target_fn,
        data=config.dataset_name,
        evaluators=config.evaluators,
        experiment_prefix=config.experiment_prefix,
        project_name=os.environ.get("LANGSMITH_PROJECT"),
    )

    # --- Collect scores from all examples and evaluators ---------------------
    scores: list[float] = []
    async for row in results:
        run = row["run"]
        assert run.error is None, f"Agent run raised an error:\n{run.error}"

        eval_results: list[EvaluationResult] = row["evaluation_results"]["results"]
        for er in eval_results:
            if er.score is not None:
                scores.append(float(er.score))

    avg = sum(scores) / len(scores) if scores else 0.0
    return EvalResult(
        passed=avg >= config.pass_threshold,
        avg_score=avg,
        scores=scores,
        experiment_name=results.experiment_name,
    )
