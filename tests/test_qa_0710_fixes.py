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
    votes = judged["votes"]
    assert len(votes) == 3
    assert votes[0]["task_completion"]["choice"] == "Not completed"
    assert votes[0]["task_completion"]["confidence"] == 0.2
    assert votes[1]["task_completion"]["choice"] == "Fully completed"
    assert votes[2]["task_completion"]["choice"] == "Fully completed"


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


def test_history_show_prints_named_red_offline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import plain_text
    from typer.testing import CliRunner

    from skillgate_ai.cli import app
    from skillgate_ai.history import append_eval

    pack = tmp_path / "skills" / "refunds"
    (pack / "evals").mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        "---\nname: refunds\ndescription: Handle refunds.\n---\n# refunds\n",
        encoding="utf-8",
    )
    append_eval(
        pack,
        run_id="red-1",
        passed=False,
        report={
            "tasks": [
                {
                    "id": "escalate-refund",
                    "passed": False,
                    "failures": ["This check did not pass."],
                    "happened": (
                        "Got the job done? Not completed (need Fully completed) — "
                        "The refund is impossible, so the bot told the customer."
                    ),
                }
            ],
            "task_count": 1,
            "passed_count": 0,
        },
    )
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = CliRunner().invoke(app, ["history", "show", "red-1", "--pack", str(pack)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "Got the job done?" in out
    assert "refund is impossible" in out
    assert "This check did not pass." not in out


def _jev_choice_answers(
    choices: dict[str, str] | None = None, *, confidence: float = 0.9
) -> dict[str, dict[str, object]]:
    from test_judge_openai import PASS_CHOICES

    merged = {**PASS_CHOICES, **(choices or {})}
    return {
        key: {"type": "choice", "choice": value, "confidence": confidence}
        for key, value in merged.items()
    }


def _jev_judge(post: FakePost):
    from skillgate_ai.judge_openai import OutcomeJudge
    from skillgate_ai.judge_providers.jev import JevBackend

    backend = JevBackend(
        api_key="jev-key",
        base_url="https://openrouter.ai/api/v1",
        model="typesafe/jev-1.14",
        post=post,
    )
    return OutcomeJudge(
        backend,
        display_name="the judge",
        provider="jev",
        chosen=True,
        supports_why=False,
        supports_confidence=False,
    )


def test_jev_500_is_retried_and_then_scores(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skillgate_ai.judge_spec import resolve_judge_spec

    monkeypatch.setattr("skillgate_ai.openai_http.time.sleep", lambda _s: None)
    post = FakePost(
        [
            FakeResponse(500, {"error": {"message": "upstream"}}),
            FakeResponse(200, {"model": "typesafe/jev-1.14", "answers": _jev_choice_answers()}),
        ]
    )
    judged = _jev_judge(post).judge(
        "goal",
        [],
        "tail",
        spec=resolve_judge_spec(),
        path={"had_path": True, "steps": 1},
    )
    assert judged["status"] == "completed"
    assert judged["passed"] is True
    assert len(post.calls) == 2
    blob = json.dumps(judged)
    assert "Scoring failed." not in blob
    assert "OpenRouter" not in blob
    assert "Jev" not in blob


def test_jev_scoring_failure_names_a_retryable_cause_not_scoring_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from skillgate_ai.judge_providers.jev import _public_failure
    from skillgate_ai.judge_spec import resolve_judge_spec

    monkeypatch.setattr("skillgate_ai.openai_http.time.sleep", lambda _s: None)
    post = FakePost(
        [
            FakeResponse(500, {"error": {"message": "upstream"}}),
            FakeResponse(502, {"error": {"message": "bad gateway"}}),
            FakeResponse(503, {"error": {"message": "unavailable"}}),
        ]
    )
    judged = _jev_judge(post).judge(
        "goal",
        [],
        "tail",
        spec=resolve_judge_spec(),
        path={"had_path": True, "steps": 1},
    )
    assert judged["status"] == "error"
    reasons = " ".join(str(item) for item in (judged.get("reasons") or []))
    reason = str(judged.get("reason") or "")
    blob = f"{reasons} {reason}"
    assert "Scoring failed." not in blob
    assert "couldn't score" in blob.lower() or "temporary" in blob.lower()
    assert "500" not in blob
    assert "HTTP" not in blob
    assert "OpenRouter" not in blob
    assert "Jev" not in blob
    assert len(post.calls) == 3
    public = _public_failure({"http_status": 500, "reason": "The judge couldn't score this check."})
    assert public != "Scoring failed."
    assert "500" not in public


def test_jev_ping_retries_transient_500(monkeypatch: pytest.MonkeyPatch) -> None:
    from skillgate_ai.judge_providers.jev import JevBackend

    monkeypatch.setattr("skillgate_ai.openai_http.time.sleep", lambda _s: None)
    post = FakePost(
        [
            FakeResponse(500, {"error": {"message": "upstream"}}),
            FakeResponse(200, {"model": "typesafe/jev-1.14", "answers": {}}),
        ]
    )
    result = JevBackend(
        api_key="jev-key",
        base_url="https://openrouter.ai/api/v1",
        model="typesafe/jev-1.14",
        post=post,
    ).ping()
    assert result["ok"] is True
    assert len(post.calls) == 2


def test_scoring_error_exits_2_not_a_quality_red(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from conftest import enable_cursor_agent
    from skillgate_ai.gate import run_check
    from skillgate_ai.scorers import Score

    root = Path(__file__).resolve().parents[1]
    enable_cursor_agent(monkeypatch, tmp_path)
    dest = tmp_path / "pdf"
    shutil.copytree(root / "skills" / "pdf", dest)

    class StubHarness:
        name = "cursor-agent"

        def run(self, *args, **kwargs):
            raise AssertionError("run_eval is stubbed")

    def fake_run_eval(*_args, **_kwargs) -> SuiteReport:
        task = TaskReport(
            task_id="escalate-refund",
            prompt="Refund this order.",
            expect_skill="pdf",
            passed=False,
            scores=[
                Score(
                    scorer="skill_trigger",
                    passed=True,
                    detail="Triggered `pdf`",
                    expected="pdf",
                    actual="pdf",
                )
            ],
            selected_skill="pdf",
            failures=["Scoring failed."],
            judge={
                "status": "error",
                "provider": "jev",
                "passed": None,
                "quality_unscored": True,
                "reasons": ["Scoring failed."],
                "reason": "Scoring failed.",
            },
        )
        return SuiteReport(
            suite="pdf-pack",
            title="Dataset",
            skill="pdf",
            harness="cursor-agent",
            sandbox="local",
            passed=False,
            tasks=[task],
            skill_path=str(dest),
            config={"judge": {"provider": "jev", "display_name": "the judge"}},
        )

    class StubJudge:
        name = "jev"
        display_name = "the judge"

    monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *_a, **_k: StubHarness())
    monkeypatch.setattr("skillgate_ai.gate.resolve_judge", lambda *_a, **_k: StubJudge())
    monkeypatch.setattr("skillgate_ai.gate.judge_stamp", lambda _j: {"provider": "jev"})
    monkeypatch.setattr("skillgate_ai.gate.run_eval", fake_run_eval)
    result = run_check(dest, source="test", root=tmp_path)
    assert result.exit_code == 2
    assert result.report is not None
    assert result.report.passed is False


def test_jev_low_confidence_blocking_adherence_is_reasked_and_records_votes() -> None:
    from skillgate_ai.judge_spec import resolve_judge_spec

    post = FakePost(
        [
            FakeResponse(
                200,
                {
                    "model": "typesafe/jev-1.14",
                    "answers": _jev_choice_answers(
                        {"instruction_adherence": "Major deviation"}, confidence=0.33
                    ),
                },
            ),
            FakeResponse(
                200,
                {
                    "model": "typesafe/jev-1.14",
                    "answers": _jev_choice_answers(confidence=0.86),
                },
            ),
            FakeResponse(
                200,
                {
                    "model": "typesafe/jev-1.14",
                    "answers": _jev_choice_answers(confidence=0.91),
                },
            ),
        ]
    )
    judged = _jev_judge(post).judge(
        "goal",
        [],
        "tail",
        spec=resolve_judge_spec(),
        path={"had_path": True, "steps": 1},
    )
    assert judged["passed"] is True
    assert judged["answers"]["instruction_adherence"]["choice"] == "Fully followed"
    assert len(post.calls) == 3
    votes = judged["votes"]
    assert len(votes) == 3
    assert votes[0]["instruction_adherence"]["choice"] == "Major deviation"
    assert votes[0]["instruction_adherence"]["confidence"] == 0.33
