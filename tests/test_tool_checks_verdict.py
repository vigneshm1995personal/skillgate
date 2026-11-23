"""Tool checks outrank judge in engine path."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import skillgate_ai.engine.task as task_mod
from skillgate_ai.engine.verdict import _apply_tool_failures
from skillgate_ai.harness import HarnessResult
from skillgate_ai.scorers import ScorerSpec, TriggerEvidence
from skillgate_ai.suite import TaskSpec
from skillgate_ai.tool_check_schema import TaskToolChecks


def _write_calls_log(ws: Path, rows: list[dict]) -> None:
    dest = ws / "output"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "calls.log").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_apply_tool_failures_order_and_dedupe() -> None:
    failures = ["det", "T"]
    passed, out, judged = _apply_tool_failures(True, failures, {"passed": True}, ["T"])
    assert passed is False
    assert out == ["T", "det"]
    passed2, failures2, judged2 = _apply_tool_failures(True, failures, judged, [])
    assert passed2 is True
    assert failures2 is failures
    assert judged2 is judged


def test_tool_failure_outranks_green_judge(tmp_path: Path, monkeypatch: Any) -> None:
    _write_calls_log(tmp_path, [{"tool": "stripe_refunds_create", "args": {"charge": "ch_1"}}])
    monkeypatch.setattr(
        task_mod,
        "_run_outcome_judge",
        lambda *a, **k: (
            {"passed": True, "reasons": [], "review": True},
            None,
            None,
            None,
        ),
    )
    explain_calls: list[bool] = []

    def _explain(_judge, passed, _failures, judged, **_k):
        explain_calls.append(passed)
        return judged

    monkeypatch.setattr(task_mod, "_maybe_explain_fail", _explain)
    task = TaskSpec(
        id="c",
        prompt="p",
        expect_skill="demo",
        scorers=[ScorerSpec(type="skill_trigger")],
        tool_checks=TaskToolChecks(),
    )
    result = HarnessResult(
        trigger=TriggerEvidence(selected_skill="demo"),
        transcript="",
        spans=[],
    )
    _, _, passed, failures, judged, review, _ = task_mod._score_and_judge_task(
        task,
        sandbox=SimpleNamespace(workspace=tmp_path),
        result=result,
        skills=[],
        harness=SimpleNamespace(name="cursor-agent"),
        judge=None,
        skill_root=None,
        file_baseline={},
    )
    assert passed is False
    assert failures[0].startswith("Unrequested consequential call: stripe_refunds_create")
    assert isinstance(judged, dict)
    assert judged["passed"] is True
    assert judged.get("tool_checks_failed") is True
    assert review is False
    assert explain_calls == [False]
