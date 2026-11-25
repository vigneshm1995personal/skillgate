from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from skillgate_ai.scorers import Score
from skillgate_ai.suite import TaskSpec
from skillgate_ai.tool_check_schema import TaskToolChecks, declared_patterns
from skillgate_ai.tool_checks.assertions import _score_assertions
from skillgate_ai.tool_checks.collect import collect_tool_calls
from skillgate_ai.tool_checks.consequential import _score_consequential
from skillgate_ai.tool_checks.rules import TOOL_CHECK_SCORERS


def score_tool_checks(
    task: TaskSpec,
    workspace: Path,
    *,
    spans: Sequence[Mapping[str, Any]] | None,
    transcript: str,
) -> list[Score]:
    checks = task.tool_checks if task.tool_checks is not None else TaskToolChecks()
    if task.expect_skill is None:
        checks = checks.model_copy(update={"must_call": []})
    declared = declared_patterns(checks)
    calls = collect_tool_calls(
        workspace,
        spans,
        transcript,
        calls_log=checks.calls_log,
        declared=declared,
    )
    scores: list[Score] = []
    if checks.must_call or checks.must_not_call:
        scores.append(_score_assertions(checks, calls))
    if not checks.skip_consequential_check:
        scores.append(_score_consequential(checks, calls))
    from skillgate_ai.scorers import headline_for

    for score in scores:
        score.headline = headline_for(score)
    return scores


def tool_check_failures(scores: Sequence[Score]) -> list[str]:
    out: list[str] = []
    for score in scores:
        if score.scorer not in TOOL_CHECK_SCORERS or score.passed:
            continue
        headline = (score.headline or score.detail or "").strip()
        if headline:
            out.append(headline)
    return out
