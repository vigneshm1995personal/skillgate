from __future__ import annotations

import pytest

from skillgate_ai.metrics import (
    CaseBudgets,
    budget_gate_reason,
    count_path_steps,
    evaluate_task_metrics,
    merge_budgets,
    metrics_blocking,
    parse_budgets,
    suite_metrics_summary,
)


def test_case_budgets_rejects_non_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        CaseBudgets(max_steps=0)


def test_parse_and_merge_budgets() -> None:
    assert parse_budgets(None) is None
    assert merge_budgets({"max_steps": 5}, {"tokens_total": 10}) == CaseBudgets(
        max_steps=5, tokens_total=10
    )


def test_count_path_steps_from_spans_and_transcript() -> None:
    spans = [
        {"name": "tool.bash", "attributes": {}},
        {"name": "skill.load", "attributes": {}},
    ]
    assert count_path_steps(spans, "$ make\nchanged a.py")[0] >= 1


def test_evaluate_task_metrics_flags_token_budget() -> None:
    metrics = evaluate_task_metrics(
        usage={"tokens_total": 20},
        spans=[],
        transcript="",
        budgets=CaseBudgets(tokens_total=5),
    )
    assert metrics["blocking"] is True
    assert metrics["status"] == "fail"


def test_metrics_blocking_and_gate_reason() -> None:
    task_metrics = evaluate_task_metrics(
        usage={"tokens_total": 9},
        spans=[],
        transcript="",
        budgets=CaseBudgets(tokens_total=1),
    )
    report = {
        "tasks": [{"id": "a", "metrics": task_metrics}],
        "metrics": suite_metrics_summary([{"id": "a", "metrics": task_metrics}]),
    }
    assert metrics_blocking(report) is True
    assert "token" in budget_gate_reason(report).lower()
