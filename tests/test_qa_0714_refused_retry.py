"""0.7.14: duplicate-refund check counts succeeded refunds, not attempts."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_qa_56_round4 import C8_DUP_ASK, _call, _extra_spec, _outputs, _pass_answers
from test_qa_56_round6 import _scores

from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.judge_bank import GUARD_REFUSED_RETRY_NOTE
from skillgate_ai.judge_spec import spec_verdict
from skillgate_ai.report import format_cli, report_to_dict
from skillgate_ai.run_details import format_run_show
from skillgate_ai.span_facts import apply_log_facts, resolve_log_facts


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _q20_rep3_c8_log(*, second_succeeded: bool) -> str:
    """Botpress c8: first refund went through; second attempt is a retry."""
    first = _call(
        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
        {"http_status": 200, "status": "succeeded", "amount": "49.00"},
    )
    if second_succeeded:
        second = _call(
            ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
            {"http_status": 200, "status": "succeeded", "amount": "49.00"},
        )
    else:
        second = _call(
            ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
            {
                "http_status": 409,
                "status": "failed",
                "error": {
                    "code": "lookup_required",
                    "message": "lookup_required: confirm the charge before retrying",
                },
            },
        )
    lookup = _call(
        ["lookup", "dana.okafor@lumenfit.co"],
        {
            "http_status": 200,
            "charges": [
                {
                    "id": "ch_3QX81",
                    "amount_refunded": "98.00" if second_succeeded else "49.00",
                    "refunds": (
                        [
                            {"id": "re_1", "amount": "49.00", "status": "succeeded"},
                            {"id": "re_2", "amount": "49.00", "status": "succeeded"},
                        ]
                        if second_succeeded
                        else [{"id": "re_1", "amount": "49.00", "status": "succeeded"}]
                    ),
                }
            ],
        },
    )
    return f"{first}\n{second}\n{lookup}"


def _c8_outputs(log: str) -> list[dict[str, str]]:
    return _outputs(
        ("output/calls.log", log),
        ("output/reply.txt", "I've processed a full refund of USD 49.00."),
    )


def _score_c8(log: str) -> tuple[dict, bool, list[str], list[str], dict]:
    spec = _extra_spec(C8_DUP_ASK)
    outputs = _c8_outputs(log)
    facts = resolve_log_facts(spec, [], outputs=outputs)
    merged = apply_log_facts(spec, _pass_answers(), [], outputs=outputs)
    passed, reasons, warnings = spec_verdict(spec, merged, supports_confidence=True)
    return facts, passed, reasons, warnings, merged


def test_guard_refused_retry_is_a_warning_not_a_fail() -> None:
    facts, passed, reasons, warnings, merged = _score_c8(_q20_rep3_c8_log(second_succeeded=False))
    assert facts["q0"]["probability"] == 1.0
    assert facts["q0"]["source"] == "log"
    assert facts["q0"].get("warning") == GUARD_REFUSED_RETRY_NOTE
    assert passed is True
    assert not any("no duplicate refund" in item.lower() for item in reasons)
    assert GUARD_REFUSED_RETRY_NOTE in warnings
    task = TaskReport(
        task_id="c8",
        prompt="pending refund",
        expect_skill="ticket-deflector",
        passed=True,
        scores=_scores(),
        selected_skill="ticket-deflector",
        judge={
            "passed": True,
            "warnings": warnings,
            "answers": merged,
            "cells": {
                "q0": {**merged["q0"], "label": C8_DUP_ASK, "choice": "Yes"},
            },
        },
    )
    report = SuiteReport(
        suite="suite",
        title="Refund desk",
        skill="ticket-deflector",
        harness="cursor-agent",
        sandbox="local",
        passed=True,
        tasks=[task],
    )
    cli = format_cli(report)
    assert GUARD_REFUSED_RETRY_NOTE in cli
    blob = report_to_dict(report)
    assert blob["tasks"][0]["happened"] == GUARD_REFUSED_RETRY_NOTE
    text = format_run_show(
        {
            "run_id": "q20-rep3-c8",
            "passed": True,
            "report": {
                "gate": "green",
                "passed": True,
                "passed_count": 1,
                "task_count": 1,
                "tasks": [
                    {
                        "id": "c8",
                        "name": "c8",
                        "passed": True,
                        "happened": GUARD_REFUSED_RETRY_NOTE,
                        "judge": task.judge,
                    }
                ],
            },
        },
        detail=True,
    )
    assert GUARD_REFUSED_RETRY_NOTE in text


def test_two_succeeded_refunds_still_fail() -> None:
    facts, passed, reasons, warnings, _merged = _score_c8(
        _q20_rep3_c8_log(second_succeeded=True)
    )
    assert facts["q0"]["probability"] == 0.0
    assert facts["q0"]["source"] == "log"
    assert facts["q0"].get("warning") in (None, "")
    assert passed is False
    assert any("no duplicate refund" in item.lower() for item in reasons)
    assert GUARD_REFUSED_RETRY_NOTE not in warnings
