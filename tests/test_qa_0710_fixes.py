"""QA for 0.7.10: expected-outcome judging, low-confidence majority, named reds."""

from __future__ import annotations

import json
import re
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


def test_jev_ping_does_not_retry_transient_500(monkeypatch: pytest.MonkeyPatch) -> None:
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
    assert result["ok"] is False
    assert len(post.calls) == 1


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


def _official_openrouter_200(answers: dict[str, dict[str, object]]) -> dict[str, object]:
    """Documented Decisions 200: top-level answers, dict probabilities, usage.cost."""
    return {
        "id": "gen-dec-1790265859-EaXKST7hul1Wcqots1ZK",
        "model": "typesafe/jev-1.14-20261001",
        "provider": "TypeSafe",
        "answers": answers,
        "usage": {"input_tokens": 476, "output_tokens": 70, "cost": 0.000019992},
    }


def _official_choice_answers(choices: dict[str, str] | None = None) -> dict[str, dict[str, object]]:
    from test_judge_openai import PASS_CHOICES

    merged = {**PASS_CHOICES, **(choices or {})}
    rows: dict[str, dict[str, object]] = {}
    for key, value in merged.items():
        rows[key] = {
            "type": "choice",
            "choice": value,
            "confidence": 0.91,
            "probabilities": {value: 0.91},
        }
    return rows


def _production_jev(post: FakePost):
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
        supports_confidence=True,
    )


def test_jev_official_200_scores_the_real_openrouter_request_shape() -> None:
    calls: list[dict] = []

    def post(url, headers=None, json=None, timeout=None):
        del headers, timeout
        body = json or {}
        calls.append({"url": str(url), "json": body})
        questions = body.get("questions") if isinstance(body.get("questions"), dict) else {}
        if "connection_test" in questions and set(questions) == {"connection_test"}:
            return FakeResponse(
                200,
                _official_openrouter_200(
                    {"connection_test": {"type": "noul", "noul": 0.99}}
                ),
            )
        return FakeResponse(200, _official_openrouter_200(_official_choice_answers()))

    from skillgate_ai.judge_providers.jev import JevBackend
    from skillgate_ai.judge_spec import resolve_judge_spec

    backend = JevBackend(
        api_key="jev-key",
        base_url="https://openrouter.ai/api/v1",
        model="typesafe/jev-1.14",
        post=post,
    )
    ping = backend.ping()
    assert ping["ok"] is True, ping
    ping_body = calls[0]["json"]
    assert calls[0]["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert ping_body["model"] == "typesafe/jev-1.14"
    assert ping_body["state"] == "ping"
    assert "input" not in ping_body
    assert ping_body["questions"]["connection_test"]["type"] == "noul"
    assert set(ping_body["questions"]["connection_test"]["criteria"]) == {"true", "false"}
    assert "supports_confidence" not in ping_body

    judged = _production_jev(post).judge(
        "goal",
        [],
        "tail",
        spec=resolve_judge_spec(),
        path={"had_path": True, "steps": 1},
    )
    eval_body = calls[1]["json"]
    assert isinstance(eval_body["state"], str) and eval_body["state"]
    assert eval_body["questions"]["task_completion"]["type"] == "choice"
    assert "Fully completed" in eval_body["questions"]["task_completion"]["criteria"]
    assert "supports_confidence" not in eval_body
    assert judged["status"] == "completed"
    assert judged["passed"] is True
    task = judged["answers"]["task_completion"]
    assert task["choice"] == "Fully completed"
    assert task["confidence"] == 0.91
    assert task["probabilities"][0]["value"] == "Fully completed"
    blob = json.dumps(judged)
    assert "TypeSafe" not in blob
    assert "OpenRouter" not in blob
    assert "Jev" not in blob
    assert len(calls) == 2


def test_jev_200_error_envelope_is_a_scoring_failure_not_connected() -> None:
    from skillgate_ai.judge_spec import resolve_judge_spec

    payload = {
        "id": "gen-dec-error",
        "error": {
            "message": "OpenRouter: Invalid schema for questions.connection_test sk-or-v1-secret",
            "code": 400,
        },
    }
    post = FakePost([FakeResponse(200, payload), FakeResponse(200, payload)])
    from skillgate_ai.judge_providers.jev import JevBackend

    ping = JevBackend(
        api_key="sk-or-v1-secret",
        base_url="https://openrouter.ai/api/v1",
        model="typesafe/jev-1.14",
        post=post,
    ).ping()
    assert ping["ok"] is False
    message = str(ping.get("message") or "")
    assert "OpenRouter" not in message
    assert "sk-or-v1-secret" not in message
    judged = _production_jev(post).judge(
        "goal",
        [],
        "tail",
        spec=resolve_judge_spec(),
        path={"had_path": True, "steps": 1},
    )
    assert judged["status"] == "error"
    blob = json.dumps(judged)
    assert "OpenRouter" not in blob
    assert "sk-or-v1-secret" not in blob


def test_jev_verbose_shows_sanitized_upstream_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import plain_text
    from typer.testing import CliRunner

    from skillgate_ai.cli import app
    from skillgate_ai.keys import set_vault_key

    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    set_vault_key(tmp_path, "JEV_API_KEY", "sk-or-v1-secret")
    runner = CliRunner()
    saved = runner.invoke(app, ["judge", "provider", "set", "jev"])
    assert saved.exit_code == 0, saved.stdout + saved.stderr

    def post(url, headers=None, json=None, timeout=None):
        del url, headers, json, timeout
        return FakeResponse(
            400,
            {
                "error": {
                    "message": "OpenRouter rejected questions.task_completion criteria sk-or-v1-secret"
                }
            },
        )

    monkeypatch.setattr("skillgate_ai.openai_http.httpx.post", post)
    quiet = runner.invoke(app, ["judge", "test"])
    quiet_out = plain_text(quiet.stdout + quiet.stderr)
    assert quiet.exit_code == 1, quiet_out
    assert "OpenRouter" not in quiet_out
    assert "sk-or-v1-secret" not in quiet_out
    verbose = runner.invoke(app, ["judge", "test", "--verbose"])
    verbose_out = plain_text(verbose.stdout + verbose.stderr)
    assert verbose.exit_code == 1, verbose_out
    assert "criteria" in verbose_out.lower()
    assert "OpenRouter" not in verbose_out
    assert "sk-or-v1-secret" not in verbose_out
    assert "Jev" not in verbose_out


def test_scoring_outage_json_and_history_say_not_scored_not_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from conftest import enable_cursor_agent, plain_text
    from typer.testing import CliRunner

    from skillgate_ai.cli import app
    from skillgate_ai.engine import _live_verdict
    from skillgate_ai.gate import persist_eval
    from skillgate_ai.history import load_history
    from skillgate_ai.report import format_cli, report_to_dict
    from skillgate_ai.scorers import Score

    passed, failures, judged = _live_verdict(
        {
            "status": "error",
            "provider": "jev",
            "reasons": ["The judge couldn't score this check. Retry — this is often temporary."],
            "upstream": "Invalid schema for questions.task_completion criteria",
        },
        "pdf",
        det_passed=True,
        det_failures=[],
    )
    assert passed is None
    assert judged is not None
    assert judged.get("quality_unscored") is True
    task = TaskReport(
        task_id="extract-pdf",
        prompt="extract",
        expect_skill="pdf",
        passed=passed,
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
        failures=failures,
        judge=judged,
    )
    report = SuiteReport(
        suite="pdf-pack",
        title="Dataset",
        skill="pdf",
        harness="cursor-agent",
        sandbox="local",
        passed=None,
        tasks=[task],
        skill_path=str(tmp_path / "pdf"),
        config={"judge": {"provider": "jev", "display_name": "the judge"}},
    )
    payload = report_to_dict(report)
    assert payload["passed"] is None
    assert payload["gate"] == "not scored"
    assert payload["tasks"][0]["passed"] is None
    happened = str(payload["tasks"][0].get("happened") or "").lower()
    assert happened == "not scored"
    assert payload["gate"] != "red"
    text = format_cli(report).lower()
    assert "not scored" in text
    assert "gate is red" not in text

    pack = tmp_path / "skills" / "pdf"
    (pack / "evals").mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: Read PDFs.\n---\n# pdf\n",
        encoding="utf-8",
    )
    persist_eval(
        pack_root=pack,
        run_id="outage-1",
        passed=None,
        report=payload,
        config={"judge": {"provider": "jev"}},
    )
    rows = load_history(pack, limit=1)
    assert rows
    assert rows[0].get("passed") is None
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    enable_cursor_agent(monkeypatch, tmp_path)
    shown = CliRunner().invoke(app, ["history", "show", "outage-1", "--pack", str(pack)])
    listed = CliRunner().invoke(app, ["history", "--pack", str(pack)])
    shown_out = plain_text(shown.stdout + shown.stderr)
    listed_out = plain_text(listed.stdout + listed.stderr)
    assert shown.exit_code == 0, shown_out
    assert listed.exit_code == 0, listed_out
    assert "not scored" in shown_out.lower()
    assert "not scored" in listed_out.lower()
    assert "  fail" not in shown_out.lower()
    assert re.search(r"\bfail\b", listed_out.lower()) is None
    json_shown = CliRunner().invoke(
        app, ["history", "show", "outage-1", "--pack", str(pack), "--json"]
    )
    json_blob = json_shown.stdout or ""
    assert "not scored" in json_blob.lower()
    parsed = json.loads(json_blob)
    assert parsed.get("passed") is None
    assert parsed.get("gate") != "red"
    report_gate = (parsed.get("report") or {}).get("gate")
    assert report_gate == "not scored"
