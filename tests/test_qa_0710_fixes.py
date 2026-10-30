"""QA for 0.7.10: expected-outcome judging, low-confidence majority, named reds."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_judge_openai import (
    FakePost,
    FakeResponse,
    _judge,
    _score,
    decisions_payload,
)

from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.judge_bank import OUTCOME_QUESTIONS, OUTCOME_SCORING_NOTES
from skillgate_ai.report import format_cli, format_github, report_to_dict

ESCALATION_OUTCOME = (
    "Refund is impossible. Tell the customer honestly and write an owner report."
)


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def test_tests_do_not_use_the_real_home_dir(tmp_path: Path) -> None:
    home = Path.home()
    assert home == tmp_path / "home"
    assert str(home).startswith(str(tmp_path))
    assert home != Path("/root")
    assert home != Path("/home/ubuntu")


def test_general_checks_treat_expected_escalation_as_done() -> None:
    fully = str(OUTCOME_QUESTIONS["task_completion"]["criteria"]["Fully completed"])
    blob = f"{fully}\n{OUTCOME_SCORING_NOTES}".lower()
    assert "expected outcome" in blob
    assert "escalat" in blob
    assert "refus" in blob
    post = FakePost([FakeResponse(200, decisions_payload())])
    judged = _score(
        _judge(post),
        golden={"body": ESCALATION_OUTCOME, "kind": "text"},
    )
    assert judged["status"] == "completed"
    payload = post.calls[0]["json"]
    raw_input = payload["input"]
    text = raw_input if isinstance(raw_input, str) else json.dumps(raw_input)
    state = json.loads(text)
    assert ESCALATION_OUTCOME in str(state.get("expected_outcome") or "")
    task_q = next(item for item in payload["questions"] if item["name"] == "task_completion")
    fully_choice = next(
        row for row in task_q["choices"] if row["value"] == "Fully completed"
    )
    description = str(fully_choice.get("description") or "").lower()
    assert "expected outcome" in description
    assert "escalat" in description or "refus" in description


def test_low_confidence_fail_is_reasked_and_majority_passes() -> None:
    post = FakePost(
        [
            FakeResponse(
                200,
                decisions_payload({"task_completion": "Not completed"}, confidence=0.2),
            ),
            FakeResponse(200, decisions_payload(confidence=0.86)),
            FakeResponse(200, decisions_payload(confidence=0.91)),
        ]
    )
    judged = _score(_judge(post))
    assert judged["passed"] is True
    assert judged["answers"]["task_completion"]["choice"] == "Fully completed"
    assert len(post.calls) == 3


def test_low_confidence_majority_fail_keeps_the_pass_mark() -> None:
    post = FakePost(
        [
            FakeResponse(
                200,
                decisions_payload({"task_completion": "Not completed"}, confidence=0.15),
            ),
            FakeResponse(200, decisions_payload(confidence=0.88)),
            FakeResponse(
                200,
                decisions_payload({"task_completion": "Not completed"}, confidence=0.22),
            ),
        ]
    )
    judged = _score(_judge(post))
    assert judged["passed"] is False
    assert judged["answers"]["task_completion"]["choice"] == "Not completed"
    assert any("Got the job done?" in item for item in judged["reasons"])
    assert len(post.calls) == 3


def test_high_confidence_fail_is_not_reasked() -> None:
    post = FakePost(
        [
            FakeResponse(
                200,
                decisions_payload({"task_completion": "Not completed"}, confidence=0.92),
            )
        ]
    )
    judged = _score(_judge(post))
    assert judged["passed"] is False
    assert len(post.calls) == 1


def _red_task() -> TaskReport:
    reason = (
        "Got the job done? Not completed (need Fully completed) — "
        "The refund is impossible, so the bot told the customer and wrote an owner report."
    )
    return TaskReport(
        task_id="escalate-refund",
        prompt="Refund this order.",
        expect_skill="refunds",
        passed=False,
        scores=[],
        selected_skill="refunds",
        failures=["This check did not pass."],
        judge={
            "status": "completed",
            "passed": False,
            "provider": "openai",
            "display_name": "the judge",
            "reasons": [reason],
            "why": None,
            "cells": {
                "task_completion": {
                    "label": "Got the job done?",
                    "choice": "Not completed",
                    "reason": (
                        "The refund is impossible, so the bot told the customer "
                        "and wrote an owner report."
                    ),
                }
            },
        },
    )


def test_red_names_failing_check_and_includes_judge_reason() -> None:
    report = SuiteReport(
        suite="suite",
        title="Refunds",
        skill="refunds",
        harness="cursor-agent",
        sandbox="local",
        passed=False,
        tasks=[_red_task()],
    )
    cli = format_cli(report)
    gh = format_github(report)
    happened = report_to_dict(report)["tasks"][0]["happened"]
    for blob in (cli, gh, happened):
        assert "Got the job done?" in blob
        assert "refund is impossible" in blob
        assert "This check did not pass." not in blob
    assert "OpenAI" not in cli
    assert "Jev" not in cli
