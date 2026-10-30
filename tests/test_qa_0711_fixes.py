"""QA for 0.7.11: low-confidence review status and log-fact custom checks."""

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
from skillgate_ai.judge_bank import UNSURE_REVIEW
from skillgate_ai.judge_spec import (
    JudgeQuestion,
    JudgeSpec,
    builtin_questions,
    extra_question_passed,
    spec_verdict,
)
from skillgate_ai.report import format_cli, format_github, report_to_dict
from skillgate_ai.span_facts import apply_log_facts, count_tool_calls, resolve_log_facts

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "q10"


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _spec_from_fixture(blob: dict) -> JudgeSpec:
    extras: list[JudgeQuestion] = []
    for qid, row in (blob.get("extra_questions") or {}).items():
        extras.append(
            JudgeQuestion(
                id=str(qid),
                type=str(row.get("type") or "predicate"),
                ask=str(row.get("instructions") or ""),
            )
        )
    return JudgeSpec(questions=tuple(builtin_questions() + extras), min_confidence=0.5)


def _rescore(blob: dict) -> tuple[bool, list[str], list[str], dict]:
    spec = _spec_from_fixture(blob)
    answers = apply_log_facts(spec, blob.get("answers") or {}, blob.get("spans") or [])
    passed, reasons, warnings = spec_verdict(
        spec, answers, supports_confidence=True
    )
    return passed, reasons, warnings, answers


def _shell_span(command: str, result: str | None = None) -> dict:
    attrs = [
        {"key": "gen_ai.tool.name", "value": {"stringValue": "shell"}},
        {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": command}},
    ]
    if result is not None:
        attrs.append(
            {"key": "gen_ai.tool.call.result", "value": {"stringValue": result}}
        )
    return {"name": "tool.shell", "attributes": attrs}


def _review_task() -> TaskReport:
    return TaskReport(
        task_id="c6-success",
        prompt="Issue the refund.",
        expect_skill="ticket-deflector",
        passed=True,
        review=True,
        scores=[],
        selected_skill="ticket-deflector",
        judge={
            "status": "completed",
            "passed": True,
            "review": True,
            "provider": "openai",
            "display_name": "the judge",
            "reasons": [],
            "warnings": [UNSURE_REVIEW],
            "cells": {
                "instruction_adherence": {
                    "label": "Followed the rules?",
                    "choice": "Major deviation",
                    "confidence": 0.31,
                    "status": "unsure",
                },
                "result_quality": {
                    "label": "Delivered a good result?",
                    "choice": "Significant issues",
                    "confidence": 0.19,
                    "status": "unsure",
                },
            },
        },
    )


def test_low_confidence_majority_fail_is_unsure_not_a_gate_fail() -> None:
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
    assert judged["passed"] is True
    assert judged["review"] is True
    assert judged["answers"]["task_completion"]["choice"] == "Not completed"
    assert judged["cells"]["task_completion"]["status"] == "unsure"
    assert UNSURE_REVIEW in judged["warnings"]
    assert judged["reasons"] == []
    assert len(post.calls) == 3


def test_low_confidence_majority_fail_keeps_the_pass_mark() -> None:
    post = FakePost(
        [
            FakeResponse(
                200,
                decisions_payload({"task_completion": "Not completed"}, confidence=0.15),
            ),
            FakeResponse(
                200,
                decisions_payload({"task_completion": "Not completed"}, confidence=0.91),
            ),
            FakeResponse(
                200,
                decisions_payload({"task_completion": "Not completed"}, confidence=0.88),
            ),
        ]
    )
    judged = _score(_judge(post))
    assert judged["passed"] is False
    assert not judged.get("review")
    assert judged["answers"]["task_completion"]["choice"] == "Not completed"
    assert any("Got the job done?" in item for item in judged["reasons"])
    assert len(post.calls) == 3


def test_high_confidence_fail_still_fails_in_one_call() -> None:
    post = FakePost(
        [
            FakeResponse(
                200,
                decisions_payload({"correctness": "Incorrect"}, confidence=0.92),
            )
        ]
    )
    judged = _score(_judge(post))
    assert judged["passed"] is False
    assert not judged.get("review")
    assert len(post.calls) == 1
    assert any("Got it right?" in item for item in judged["reasons"])


def test_high_confidence_pass_does_not_flip_to_review() -> None:
    post = FakePost([FakeResponse(200, decisions_payload(confidence=0.9))])
    judged = _score(_judge(post))
    assert judged["passed"] is True
    assert not judged.get("review")
    assert judged["warnings"] == []


def test_fixture_c6_success_low_conf_fail_is_review_not_red() -> None:
    blob = _load("c6-success-rep3.json")
    passed, reasons, warnings, _ = _rescore(blob)
    assert blob["passed"] is False
    assert passed is True
    assert reasons == []
    assert UNSURE_REVIEW in warnings


def test_fixture_c4_rep2_got_it_right_at_016_is_review() -> None:
    blob = _load("c4-partial-rep2.json")
    assert blob["answers"]["correctness"]["confidence"] == 0.16
    passed, reasons, warnings, _ = _rescore(blob)
    assert passed is True
    assert reasons == []
    assert UNSURE_REVIEW in warnings


def test_fixture_c2_rep3_low_conf_fail_is_review() -> None:
    blob = _load("c2-timeout-rep3.json")
    passed, reasons, warnings, _ = _rescore(blob)
    assert blob["passed"] is False
    assert passed is True
    assert reasons == []
    assert UNSURE_REVIEW in warnings


def test_previously_passing_fixture_does_not_flip_to_fail() -> None:
    for name in ("c6-success-rep1.json", "c4-partial-rep3.json", "c2-timeout-rep1.json"):
        blob = _load(name)
        assert blob["passed"] is True
        passed, reasons, _, _ = _rescore(blob)
        assert passed is True, name
        assert reasons == [], name


def test_c8_single_refund_log_fact_overrides_judge_no() -> None:
    blob = _load("c8-duplicate-rep2.json")
    assert blob["answers"]["q0"]["probability"] == 0.74
    spec = _spec_from_fixture(blob)
    assert count_tool_calls(blob["spans"], "issue_refund") == 1
    facts = resolve_log_facts(spec, blob["spans"])
    assert "q0" in facts
    assert facts["q0"]["probability"] == 1.0
    assert "q1" not in facts
    passed, reasons, _, answers = _rescore(blob)
    ok, _ = extra_question_passed(spec.extras[0], answers["q0"])
    assert ok is True
    assert passed is True
    assert not any("no duplicate refund" in item.lower() for item in reasons)


def test_c8_rep3_single_refund_also_passes_duplicate_check() -> None:
    blob = _load("c8-duplicate-rep3.json")
    assert blob["answers"]["q0"]["probability"] == 0.78
    passed, reasons, _, _ = _rescore(blob)
    assert count_tool_calls(blob["spans"], "issue_refund") == 1
    assert passed is True
    assert not any("no duplicate refund" in item.lower() for item in reasons)


def test_duplicate_refund_from_the_log_still_fails() -> None:
    blob = _load("c8-duplicate-rep1.json")
    assert count_tool_calls(blob["spans"], "issue_refund") == 2
    passed, reasons, _, answers = _rescore(blob)
    spec = _spec_from_fixture(blob)
    ok, detail = extra_question_passed(spec.extras[0], answers["q0"])
    assert ok is False
    assert detail is not None and "No" in detail
    assert passed is False
    assert any("no duplicate refund" in item.lower() for item in reasons)


def test_synthetic_duplicate_refund_fails_without_the_judge() -> None:
    ask = (
        "[no duplicate refund calls] Answer NO if the agent called "
        "issue_refund more than once (a second call creates a second refund)."
    )
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                JudgeQuestion(
                    id="q0",
                    type="predicate",
                    ask=ask,
                )
            ]
        )
    )
    spans = [
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00"),
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00"),
    ]
    answers = {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        "q0": {"probability": 0.99, "noul": 0.99},
    }
    merged = apply_log_facts(spec, answers, spans)
    assert merged["q0"]["probability"] == 0.0
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert any("no duplicate refund" in item.lower() for item in reasons)


def test_duplicate_check_without_a_log_still_uses_the_judge() -> None:
    blob = _load("c8-duplicate-rep2.json")
    spec = _spec_from_fixture(blob)
    facts = resolve_log_facts(spec, None)
    assert facts == {}
    passed, reasons, _ = spec_verdict(
        spec, blob["answers"] or {}, supports_confidence=True
    )
    assert passed is False
    assert any("no duplicate refund" in item.lower() for item in reasons)


def test_reply_custom_check_falls_back_to_the_judge() -> None:
    blob = _load("c8-duplicate-rep2.json")
    spec = _spec_from_fixture(blob)
    facts = resolve_log_facts(spec, blob["spans"])
    assert "q1" not in facts
    answers = apply_log_facts(spec, blob["answers"], blob["spans"])
    assert answers["q1"]["probability"] == 0.93


def test_tool_return_fact_uses_span_result_not_the_judge() -> None:
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                JudgeQuestion(
                    id="q_ret",
                    type="predicate",
                    ask=(
                        "Did issue_refund return status succeeded? "
                        "Answer NO if the tool result was not succeeded."
                    ),
                )
            ]
        )
    )
    spans = [
        _shell_span(
            "python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00",
            result='{"status": "succeeded", "amount": 49.00}',
        )
    ]
    answers = {"q_ret": {"probability": 0.1, "noul": 0.1}}
    merged = apply_log_facts(spec, answers, spans)
    assert merged["q_ret"]["probability"] == 1.0
    ok, _ = extra_question_passed(spec.extras[0], merged["q_ret"])
    assert ok is True


def test_missing_tool_result_falls_back_to_the_judge() -> None:
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                JudgeQuestion(
                    id="q_ret",
                    type="predicate",
                    ask=(
                        "Did issue_refund return status succeeded? "
                        "Answer NO if the tool result was not succeeded."
                    ),
                )
            ]
        )
    )
    spans = [
        _shell_span(
            "python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00"
        )
    ]
    answers = {"q_ret": {"probability": 0.1, "noul": 0.1}}
    merged = apply_log_facts(spec, answers, spans)
    assert merged["q_ret"]["probability"] == 0.1


def test_span_facts_skip_custom_check_on_the_judge_request() -> None:
    from skillgate_ai.judge_spec import parse_extra_question

    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                parse_extra_question(
                    {
                        "id": "no_dup",
                        "type": "predicate",
                        "ask": (
                            "Answer NO if the agent called issue_refund more than once."
                        ),
                    }
                )
            ]
        )
    )
    spans = [
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00")
    ]
    extra = {
        "type": "predicate",
        "name": "no_dup",
        "probability": 0.2,
        "noul": 0.2,
    }
    payload = decisions_payload(confidence=0.91)
    payload["answers"].append(extra)
    post = FakePost([FakeResponse(200, payload)])
    judged = _score(
        _judge(post),
        spec=spec,
        spans=spans,
    )
    names = [item.get("name") for item in post.calls[0]["json"]["questions"]]
    assert "no_dup" not in names
    assert judged["answers"]["no_dup"]["probability"] == 1.0
    assert judged["answers"]["no_dup"]["source"] == "log"
    assert judged["cells"]["no_dup"]["choice"] == "Yes"
    assert judged["passed"] is True


def test_cli_json_and_happened_use_unsure_status() -> None:
    report = SuiteReport(
        suite="suite",
        title="Refunds",
        skill="ticket-deflector",
        harness="cursor-agent",
        sandbox="local",
        passed=True,
        tasks=[_review_task()],
    )
    cli = format_cli(report)
    gh = format_github(report)
    payload = report_to_dict(report)
    assert "NEEDS REVIEW" in cli
    assert "REVIEW  c6-success" in cli
    assert UNSURE_REVIEW in cli
    assert "Gate is red" not in cli
    assert "FAIL  c6-success" not in cli
    assert payload["passed"] is True
    assert payload["gate"] == "needs review"
    assert payload["tasks"][0]["status"] == "unsure"
    assert payload["tasks"][0]["review"] is True
    assert payload["tasks"][0]["passed"] is True
    assert payload["failed_task_ids"] == []
    assert payload["review_task_ids"] == ["c6-success"]
    answers = {item["label"]: item["answer"] for item in payload["tasks"][0]["check_answers"]}
    assert answers["Followed the rules?"] == UNSURE_REVIEW
    assert answers["Delivered a good result?"] == UNSURE_REVIEW
    assert UNSURE_REVIEW in gh
    assert "needs review" in gh.lower()


def test_genuinely_wrong_run_still_goes_red() -> None:
    report = SuiteReport(
        suite="suite",
        title="Refunds",
        skill="ticket-deflector",
        harness="cursor-agent",
        sandbox="local",
        passed=False,
        tasks=[
            TaskReport(
                task_id="wrong",
                prompt="Issue the refund.",
                expect_skill="ticket-deflector",
                passed=False,
                scores=[],
                selected_skill="ticket-deflector",
                failures=["Got it right? Incorrect (need Correct or Mostly correct)"],
                judge={
                    "status": "completed",
                    "passed": False,
                    "review": False,
                    "reasons": [
                        "Got it right? Incorrect (need Correct or Mostly correct) — The result is wrong."
                    ],
                    "cells": {
                        "correctness": {
                            "label": "Got it right?",
                            "choice": "Incorrect",
                            "confidence": 0.91,
                        }
                    },
                },
            )
        ],
    )
    cli = format_cli(report)
    payload = report_to_dict(report)
    assert "Gate is red" in cli
    assert "FAIL  wrong" in cli
    assert payload["gate"] == "red"
    assert payload["passed"] is False
    assert payload["tasks"][0]["status"] == "fail"


def test_low_confidence_pass_is_review_not_red() -> None:
    post = FakePost([FakeResponse(200, decisions_payload(confidence=0.2))] * 3)
    judged = _score(_judge(post))
    assert judged["passed"] is True
    assert judged["review"] is True
    assert judged["cells"]["correctness"]["status"] == "unsure"
    assert UNSURE_REVIEW in judged["warnings"]
    assert judged["reasons"] == []


def test_called_check_is_scored_from_the_log() -> None:
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                JudgeQuestion(
                    id="q_called",
                    type="predicate",
                    ask="Did the agent call `lookup_charge`? Answer NO if it never called lookup_charge.",
                )
            ]
        )
    )
    spans = [_shell_span("python3 payments_connector.py lookup_charge --charge ch_1")]
    answers = {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        "q_called": {"probability": 0.1, "noul": 0.1},
    }
    merged = apply_log_facts(spec, answers, spans)
    assert merged["q_called"]["probability"] == 1.0
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is True
    assert reasons == []


def test_forbidden_tool_call_from_the_log_still_fails() -> None:
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                JudgeQuestion(
                    id="q_called",
                    type="predicate",
                    ask="Answer NO if the agent called `issue_refund`.",
                )
            ]
        )
    )
    spans = [_shell_span("python3 payments_connector.py issue_refund --charge ch_1")]
    answers = {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        "q_called": {"probability": 0.99, "noul": 0.99},
    }
    merged = apply_log_facts(spec, answers, spans)
    assert merged["q_called"]["probability"] == 0.0
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert reasons


def test_history_records_needs_review_gate(tmp_path: Path) -> None:
    from skillgate_ai.history import append_eval, load_history

    pack = tmp_path / "pdf"
    pack.mkdir()
    append_eval(
        pack,
        run_id="review-1",
        passed=True,
        report={"gate": "needs review", "passed": True, "skill": "pdf"},
    )
    rows = load_history(pack, limit=0)
    assert rows[0]["gate"] == "needs review"
    assert rows[0]["passed"] is True


def test_needs_review_does_not_unlock_deploy() -> None:
    from skillgate_ai.deploy_gate import local_gate, run_gate_decision

    row = {
        "passed": True,
        "gate_moved": True,
        "report": {"gate": "needs review", "passed": True},
    }
    decision, reason = run_gate_decision(row)
    assert decision == "pending"
    assert "unsure" in reason.lower()
    assert local_gate(
        True, status="done", tryout=False, report={"gate": "needs review"}
    ) == (decision, reason)


def test_docs_name_the_review_status() -> None:
    judge = (ROOT / "docs" / "judge.md").read_text(encoding="utf-8")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "unsure, needs review" in judge
    assert "needs review" in changelog
    assert "spans" in changelog.lower() or "log" in changelog.lower()


def test_example_skill_goldens_still_match() -> None:
    from skillgate_ai.case_pack import load_case_pack

    pack = ROOT / "skills" / "json-response"
    loaded = load_case_pack(pack)
    assert loaded is not None
    pinned = [case for case in loaded.cases if case.status == "pinned" and case.should_trigger]
    assert pinned
    for case in pinned:
        assert case.golden is not None
        assert (pack / case.golden.path).is_file()
