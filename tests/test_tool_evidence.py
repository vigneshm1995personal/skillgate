from __future__ import annotations

from skillgate_ai.engine import _live_verdict
from skillgate_ai.judge_spec import JudgeQuestion
from skillgate_ai.scorers import Score
from skillgate_ai.tool_check_schema import TaskToolChecks, ToolCallRule
from skillgate_ai.tool_evidence import reconcile_tool_covered_extras


def _green_judge(*, extra_map: dict[str, str]) -> dict:
    cells = {
        key: {"choice": "fully completed" if key == "task_completion" else "correct"}
        for key in (
            "task_completion",
            "correctness",
            "instruction_adherence",
            "evidence_action_validity",
            "result_quality",
        )
    }
    return {
        "status": "completed",
        "passed": False,
        "extra_failures": list(extra_map.values()),
        "extra_failure_ids": dict(extra_map),
        "cells": cells,
        "reasons": list(extra_map.values()),
    }


def _tool_passing_scores() -> list[Score]:
    return [
        Score(scorer="skill_trigger", passed=True, detail="ok"),
        Score(
            scorer="tool_calls",
            passed=True,
            detail="ok",
            facts={
                "must_call_rules": [
                    {
                        "tool": "stripe_refunds_create",
                        "passed": True,
                        "min": 1,
                        "args_pinned": False,
                    }
                ]
            },
        ),
        Score(scorer="consequential_calls", passed=True, detail="ok"),
    ]


def test_c6_style_refund_predicate_does_not_block_when_must_call_passed() -> None:
    extra = {"q_did_refund_when_asked": "Did issue a refund when asked? No"}
    judged = _green_judge(extra_map=extra)
    checks = TaskToolChecks(
        must_call=[ToolCallRule(tool="stripe_refunds_create", min=1)],
    )
    extras = (
        JudgeQuestion(
            id="q_did_refund_when_asked",
            type="predicate",
            ask="Did issue a refund when asked?",
            on_fail="block",
        ),
    )
    out = reconcile_tool_covered_extras(
        judged,
        _tool_passing_scores(),
        tool_checks=checks,
        extras=extras,
    )
    assert out is not None
    assert out.get("extra_failures") == []
    assert out.get("review") is True
    passed, failures, stamped = _live_verdict(
        out,
        "billing",
        det_passed=True,
        det_failures=[],
    )
    assert passed is True
    assert failures == []
    assert stamped is not None and stamped.get("review") is True


def test_non_overlapping_blocking_predicate_still_blocks() -> None:
    extra = {"q_disclosed_fee": "Did disclose the processing fee? No"}
    judged = _green_judge(extra_map=extra)
    extras = (
        JudgeQuestion(
            id="q_disclosed_fee",
            type="predicate",
            ask="Did disclose the processing fee?",
            on_fail="block",
        ),
    )
    out = reconcile_tool_covered_extras(
        judged,
        _tool_passing_scores(),
        tool_checks=TaskToolChecks(
            must_call=[ToolCallRule(tool="stripe_refunds_create", min=1)],
        ),
        extras=extras,
    )
    passed, failures, _ = _live_verdict(out, "billing", det_passed=True, det_failures=[])
    assert passed is False
    assert failures


def test_failing_must_call_and_predicate_still_red() -> None:
    judged = _green_judge(extra_map={"q_did_refund_when_asked": "Did refund? No"})
    scores = [
        Score(scorer="skill_trigger", passed=True, detail="ok"),
        Score(
            scorer="tool_calls",
            passed=False,
            detail="Must call stripe_refunds_create: not called",
            facts={
                "must_call_rules": [
                    {"tool": "stripe_refunds_create", "passed": False, "min": 1},
                ]
            },
        ),
    ]
    out = reconcile_tool_covered_extras(
        judged,
        scores,
        tool_checks=TaskToolChecks(
            must_call=[ToolCallRule(tool="stripe_refunds_create", min=1)],
        ),
        extras=(
            JudgeQuestion(id="q_did_refund_when_asked", type="predicate", ask="x", on_fail="block"),
        ),
    )
    passed, failures, _ = _live_verdict(out, "billing", det_passed=False, det_failures=["tool"])
    assert passed is False
    assert failures
