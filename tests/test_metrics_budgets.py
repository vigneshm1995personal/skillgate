from __future__ import annotations

import pytest

from skillgate_ai.metrics import (
    REASON_BOTH_OVER,
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


def test_evaluate_task_metrics_path_budget_and_closed_path() -> None:
    over = evaluate_task_metrics(
        usage=None,
        spans=[{"name": "tool.bash", "attributes": {}}] * 6,
        transcript="",
        budgets=CaseBudgets(max_steps=2),
    )
    assert over["blocking"] is True
    assert any("step" in item.lower() for item in over["reasons"])

    closed = evaluate_task_metrics(
        usage=None,
        spans=[],
        transcript="",
        budgets=CaseBudgets(max_steps=3),
    )
    assert closed["blocking"] is True
    assert closed["reasons"]


def test_evaluate_task_metrics_both_budgets_exceeded() -> None:
    metrics = evaluate_task_metrics(
        usage={"tokens_total": 50},
        spans=[{"name": "tool.read", "attributes": {}}] * 4,
        transcript="",
        budgets=CaseBudgets(tokens_total=10, max_steps=1),
    )
    assert metrics["reasons"] == [REASON_BOTH_OVER]
    assert metrics["blocking"] is True


def test_count_path_steps_counts_gen_ai_error_spans() -> None:
    spans = [{"name": "gen_ai.error"}, {"name": "tool.bash", "attributes": {}}]
    steps, errors, had_path = count_path_steps(spans, "")
    assert errors == 1
    assert had_path is True
    assert steps == 1


def test_count_path_steps_counts_ran_exit_lines() -> None:
    steps, errors, had_path = count_path_steps(None, "ran ls exit=0")
    assert steps == 1
    assert had_path is True
    assert errors == 0


def test_suite_metrics_summary_aggregates_path_stats() -> None:
    ok = evaluate_task_metrics(
        usage={"tokens_total": 1},
        spans=[],
        transcript="",
        budgets=CaseBudgets(tokens_total=5),
    )
    summary = suite_metrics_summary(
        [
            {"id": "a", "metrics": ok},
            {"id": "b", "metrics": ok},
        ]
    )
    assert summary["status"] == "ok"
    assert "path" in summary


def test_budget_gate_reason_multi_case_and_cleared() -> None:
    fail_a = evaluate_task_metrics(
        usage={"tokens_total": 9},
        spans=[],
        transcript="",
        budgets=CaseBudgets(tokens_total=1),
    )
    fail_b = evaluate_task_metrics(
        usage={"tokens_total": 9},
        spans=[],
        transcript="",
        budgets=CaseBudgets(tokens_total=1),
    )
    multi = {
        "tasks": [
            {"id": "a", "metrics": fail_a},
            {"id": "b", "metrics": fail_b},
        ]
    }
    assert "2 cases" in budget_gate_reason(multi)
    assert budget_gate_reason({"tasks": []}) == "This Dataset passed."


def test_case_budgets_empty_and_parse_invalid() -> None:
    empty = CaseBudgets()
    assert empty.is_empty() is True
    assert parse_budgets({"tokens_total": "", "max_steps": ""}) is None
    with pytest.raises(ValueError, match="positive"):
        parse_budgets({"tokens_total": -1})
