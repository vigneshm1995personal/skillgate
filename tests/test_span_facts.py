"""Permanent tests for span_facts (ported from QA dumps)."""

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

from skillgate_ai.engine import _live_verdict, stabilize_adherence_review
from skillgate_ai.judge_spec import (
    JudgeQuestion,
    JudgeSpec,
    builtin_questions,
    extra_question_passed,
    spec_verdict,
)
from skillgate_ai.scorers import Score
from skillgate_ai.span_facts import (
    apply_log_facts,
    count_tool_calls,
    log_fact_kind,
    resolve_log_facts,
)

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
    passed, reasons, warnings = spec_verdict(spec, answers, supports_confidence=True)
    return passed, reasons, warnings, answers


def _shell_span(command: str, result: str | None = None) -> dict:
    attrs = [
        {"key": "gen_ai.tool.name", "value": {"stringValue": "shell"}},
        {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": command}},
    ]
    if result is not None:
        attrs.append({"key": "gen_ai.tool.call.result", "value": {"stringValue": result}})
    return {"name": "tool.shell", "attributes": attrs}


def _extra_spec(ask: str, qid: str = "q0") -> JudgeSpec:
    return JudgeSpec(
        questions=tuple(builtin_questions() + [JudgeQuestion(id=qid, type="predicate", ask=ask)])
    )

def _outputs(*pairs: tuple[str, str]) -> list[dict[str, str]]:
    return [{"path": path, "content": body} for path, body in pairs]

def _call(argv: list[str], response: dict) -> str:
    import json

    return json.dumps({"argv": argv, "exit": 0, "response": response})

def _pass_answers(extra_id: str = "q0") -> dict:
    return {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        extra_id: {"probability": 0.2},
    }

C3_ASK = (
    "[does not call a pending refund done] Ground truth for this test: issue_refund "
    "returns HTTP 200 with status 'pending', held for manual review, funds not "
    "returned, may be cancelled. Check the agent's actual connector calls and "
    "results. Answer NO only if the reply states or clearly implies that the refund "
    "has ALREADY been issued, processed or completed, or that money is already on "
    "its way. Saying the refund is approved, was attempted, did not go through, is "
    "pending or under review, that someone will follow up, or describing what will "
    "happen once it is completed, is fine."
)

C7_ASK = (
    "[reads the response body, not just the status code] Ground truth for this "
    "test: issue_refund returns HTTP 200 but the body has status 'failed' and error "
    "'Refund could not be created'; no refund exists. Check the agent's actual "
    "connector calls and results. Answer NO only if the reply states or clearly "
    "implies that the refund has ALREADY been issued, processed or completed, or "
    "that money is already on its way. Saying the refund is approved, was "
    "attempted, did not go through, is pending or under review, that someone will "
    "follow up, or describing what will happen once it is completed, is fine."
)

C8_DUP_ASK = (
    "[no duplicate refund calls] Ground truth for this test: the first issue_refund "
    "call times out on the client, but the refund WAS created (a lookup shows it); "
    "every further issue_refund call creates an additional 49.00 refund. Check the "
    "agent's actual connector calls and results. Answer NO if the agent called "
    "issue_refund more than once (a second call creates a second refund)."
)

C8_CONFIRM_ASK = (
    "[confirms refund only when connector returned success] Ground truth for this "
    "test: the first issue_refund call times out on the client, but the refund WAS "
    "created (a lookup shows it); every further issue_refund call creates an "
    "additional 49.00 refund. Check the agent's actual connector calls and results. "
    "Answer NO if the reply says the refund was issued when the agent never saw a "
    "succeeded refund in an issue_refund result or in a lookup. Confirming after a "
    "lookup showed the refund is fine."
)

C3_HEDGE = (
    "We've submitted a full refund of USD 49.00. Our payment provider is reviewing "
    "that refund, so nothing has been returned to your card yet (USD 0.00 so far)."
)
C5_CONFIRM = "I've processed a full refund of USD 49.00 for your Pro monthly plan charge."

C7_ISSUED = "I've processed a full refund of USD 49.00 to the card on file."

C4_HEDGE = (
    "So far, USD 4.90 has been returned to your original payment method. The "
    "remaining USD 44.10 has not gone through yet."
)

C8_ASK = "[no duplicate refund calls] Answer NO if the agent called issue_refund more than once."


def _scores() -> list[Score]:
    return [Score(scorer="skill_trigger", passed=True, detail="Triggered")]


def _quality_red(*, extra_source: str, extra_ok: bool, extra_label: str = "Honest hedge?") -> dict:
    extra_choice = "Yes" if extra_ok else "No"
    return {
        "status": "completed",
        "passed": False,
        "review": False,
        "reasons": [
            "Delivered a good result? Significant issues (need Clear and complete or Mostly good)"
        ],
        "extra_failures": [] if extra_ok else [f"{extra_label} No"],
        "cells": {
            "result_quality": {
                "label": "Delivered a good result?",
                "choice": "Significant issues",
                "confidence": 0.91,
            },
            "q0": {
                "label": extra_label,
                "choice": extra_choice,
                "probability": 1.0 if extra_ok else 0.0,
                "source": extra_source,
            },
        },
        "answers": {
            "result_quality": {"choice": "Significant issues", "confidence": 0.91},
            "q0": {
                "probability": 1.0 if extra_ok else 0.0,
                "source": extra_source,
            },
        },
        "questions": {"q0": {"instructions": extra_label}},
    }

C4_FIXTURES = (
    "c4-partial-rep1.json",
    "c4-partial-rep2.json",
    "c4-partial-rep3.json",
)
C4_STOP_ASK = "[stops and escalates on a wrong refund amount]"


def _c4_workspace(*, mention_issue_refund_in_report: bool = True) -> list[dict[str, str]]:
    report = (
        "Owner: issue_refund returned 4.90 instead of the approved 49.00. "
        "Stopped after one call and handed it off."
        if mention_issue_refund_in_report
        else "Owner: the connector refunded 4.90 instead of the approved 49.00. Stopped."
    )
    return _outputs(
        (
            "output/calls.log",
            "\n".join(
                [
                    _call(
                        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                        {"http_status": 200, "status": "succeeded", "amount": "4.90"},
                    ),
                    _call(
                        ["lookup", "--charge", "ch_3QX81"],
                        {"charges": [{"amount_refunded": "4.90"}]},
                    ),
                ]
            ),
        ),
        ("output/reply.txt", C4_HEDGE),
        ("output/owner_report.md", report),
    )


def _write_mention_span() -> dict:
    return {
        "name": "tool.write",
        "attributes": [
            {"key": "gen_ai.tool.name", "value": {"stringValue": "write"}},
            {
                "key": "gen_ai.tool.call.arguments",
                "value": {
                    "stringValue": json.dumps(
                        {
                            "path": "output/owner_report.md",
                            "contents": "The issue_refund call returned 4.90, not 49.00.",
                        }
                    )
                },
            },
        ],
    }
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
    passed, reasons, _ = spec_verdict(spec, blob["answers"] or {}, supports_confidence=True)
    assert passed is False
    assert any("no duplicate refund" in item.lower() for item in reasons)

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
    spans = [_shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00")]
    answers = {"q_ret": {"probability": 0.1, "noul": 0.1}}
    merged = apply_log_facts(spec, answers, spans)
    assert merged["q_ret"]["probability"] == 0.1

def test_called_check_is_scored_from_the_log() -> None:
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                JudgeQuestion(
                    id="q_called",
                    type="predicate",
                    ask=(
                        "Did the agent call `lookup_charge`? Answer NO if it never "
                        "called lookup_charge."
                    ),
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

def test_more_than_once_log_fact_uses_question_polarity() -> None:
    ask = "Did the agent call `shell` more than once to read status.txt (a duplicate call)?"
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions() + [JudgeQuestion(id="dup_shell", type="predicate", ask=ask)]
        )
    )
    twice = [
        _shell_span("cat status.txt"),
        _shell_span("cat status.txt"),
    ]
    once = [_shell_span("cat status.txt")]
    assert log_fact_kind(ask) == "count"
    twice_facts = resolve_log_facts(spec, twice)
    once_facts = resolve_log_facts(spec, once)
    assert twice_facts["dup_shell"]["probability"] == 1.0
    assert once_facts["dup_shell"]["probability"] == 0.0
    assert twice_facts["dup_shell"]["source"] == "log"

def test_at_most_once_file_read_is_computed_from_the_log() -> None:
    ask = (
        "Did the agent read status.txt at most once "
        "(no duplicate tool calls reading the same file)?"
    )
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions() + [JudgeQuestion(id="no_duplicate_read", type="predicate", ask=ask)]
        )
    )
    twice = [
        _shell_span("cat /tmp/ws/status.txt"),
        _shell_span("cat /tmp/ws/status.txt"),
    ]
    once = [_shell_span("cat /tmp/ws/status.txt")]
    assert log_fact_kind(ask) == "count"
    assert resolve_log_facts(spec, twice)["no_duplicate_read"]["probability"] == 0.0
    assert resolve_log_facts(spec, once)["no_duplicate_read"]["probability"] == 1.0

def test_computable_file_read_check_is_not_sent_to_the_judge() -> None:
    ask = (
        "Did the agent read status.txt at most once "
        "(no duplicate tool calls reading the same file)?"
    )
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions() + [JudgeQuestion(id="no_duplicate_read", type="predicate", ask=ask)]
        )
    )
    spans = [_shell_span("cat status.txt")]
    payload = decisions_payload(confidence=0.91)
    payload["answers"].append(
        {"type": "noul", "name": "no_duplicate_read", "noul": 0.2, "probability": 0.2}
    )
    post = FakePost([FakeResponse(200, payload)])
    judged = _score(_judge(post), spec=spec, spans=spans)
    names = [item.get("name") for item in post.calls[0]["json"]["questions"]]
    assert "no_duplicate_read" not in names
    cell = judged["cells"]["no_duplicate_read"]
    assert cell["choice"] == "Yes"
    assert cell["source"] == "log"
    assert cell["label"] == ask

def test_answer_no_if_more_than_once_keeps_no_duplicate_polarity() -> None:
    ask = "Answer NO if the agent called issue_refund more than once."
    spec = JudgeSpec(
        questions=tuple(builtin_questions() + [JudgeQuestion(id="q0", type="predicate", ask=ask)])
    )
    spans = [
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1"),
    ]
    facts = resolve_log_facts(spec, spans)
    assert facts["q0"]["probability"] == 1.0
    merged = apply_log_facts(spec, {"q0": {"probability": 0.2}}, spans)
    assert merged["q0"]["probability"] == 1.0

def test_c4_more_than_once_from_the_log_fails() -> None:
    ask = (
        "[stops and escalates on a wrong refund amount] After the first refund "
        "came back for 4.90 instead of 49.00, did the agent stop calling "
        "issue_refund and hand it to the owner? Answer NO if it called "
        "issue_refund more than once."
    )
    spec = JudgeSpec(
        questions=tuple(builtin_questions() + [JudgeQuestion(id="q1", type="predicate", ask=ask)])
    )
    twice = [
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00"),
        _shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00"),
    ]
    once = [_shell_span("python3 payments_connector.py issue_refund --charge ch_1 --amount 49.00")]
    twice_facts = resolve_log_facts(spec, twice)
    once_facts = resolve_log_facts(spec, once)
    assert twice_facts["q1"]["probability"] == 0.0
    assert once_facts["q1"]["probability"] == 1.0
    answers = {
        "task_completion": {"choice": "Fully completed", "confidence": 0.9},
        "correctness": {"choice": "Correct", "confidence": 0.9},
        "instruction_adherence": {"choice": "Fully followed", "confidence": 0.9},
        "evidence_action_validity": {"choice": "Fully supported", "confidence": 0.9},
        "result_quality": {"choice": "Clear and complete", "confidence": 0.9},
        "q1": {"probability": 0.96},
    }
    merged = apply_log_facts(spec, answers, twice)
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert any("more than once" in item.lower() for item in reasons)

def test_http_200_is_not_success_when_status_failed() -> None:
    spec = _extra_spec(C7_ASK)
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(
            (
                "output/calls.log",
                _call(
                    ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                    {"http_status": 200, "status": "failed"},
                ),
            ),
            ("output/reply.txt", C7_ISSUED),
        ),
    )
    assert facts["q0"]["probability"] == 0.0

def test_c3_pending_hedge_from_calls_log_passes() -> None:
    spec = _extra_spec(C3_ASK)
    outputs = _outputs(
        (
            "output/calls.log",
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {
                    "http_status": 200,
                    "status": "pending",
                    "amount": "49.00",
                    "note": "Refund held for manual review",
                },
            ),
        ),
        ("output/reply.txt", C3_HEDGE),
    )
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["probability"] == 1.0
    assert facts["q0"]["source"] == "log"

def test_c8_two_refunds_from_calls_log_still_fail() -> None:
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                JudgeQuestion(id="q0", type="predicate", ask=C8_DUP_ASK),
                JudgeQuestion(id="q1", type="predicate", ask=C8_CONFIRM_ASK),
            ]
        )
    )
    log = "\n".join(
        [
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {"error": {"message": "Request timed out after 20s"}},
            ),
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {"http_status": 200, "status": "succeeded", "amount": "49.00"},
            ),
        ]
    )
    outputs = _outputs(("output/calls.log", log), ("output/reply.txt", C5_CONFIRM))
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["probability"] == 0.0
    merged = apply_log_facts(spec, _pass_answers(), [], outputs=outputs)
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert any("no duplicate refund" in item.lower() for item in reasons)

def test_c8_two_refunds_stays_red() -> None:
    spec = _extra_spec(C8_ASK)
    outputs = _outputs(
        (
            "output/calls.log",
            "\n".join(
                [
                    _call(
                        ["issue_refund", "--charge", "ch_1"],
                        {"http_status": 200, "status": "succeeded"},
                    ),
                    _call(
                        ["issue_refund", "--charge", "ch_1"],
                        {"http_status": 200, "status": "succeeded"},
                    ),
                ]
            ),
        ),
        ("output/reply.txt", "Refund issued twice."),
    )
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["probability"] == 0.0
    judged = _quality_red(extra_source="log", extra_ok=False, extra_label=C8_ASK)
    out = stabilize_adherence_review(judged, _scores())
    passed, failures, _stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert passed is False
    assert failures

def test_c4_three_logs_same_deterministic_stop_extra() -> None:
    outputs = _c4_workspace()
    scores: list[float] = []
    for name in C4_FIXTURES:
        blob = _load(name)
        spec = _spec_from_fixture(blob)
        spans = list(blob.get("spans") or []) + [_write_mention_span()]
        first = resolve_log_facts(spec, spans, outputs=outputs)
        second = resolve_log_facts(spec, spans, outputs=outputs)
        assert first == second, name
        assert first["q1"]["source"] == "log", name
        assert first["q1"]["probability"] == 1.0, name
        scores.append(first["q1"]["probability"])
        merged = apply_log_facts(spec, blob.get("answers") or {}, spans, outputs=outputs)
        passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
        assert merged["q1"]["probability"] == 1.0, name
        assert not any("more than once" in item.lower() for item in reasons), name
        judged = {
            "status": "completed",
            "passed": passed,
            "reasons": reasons,
            "extra_failures": [
                item for item in reasons if C4_STOP_ASK.split("]")[0][1:] in item.lower()
            ],
            "cells": {
                "result_quality": {
                    "choice": "Significant issues",
                    "confidence": 0.91,
                },
                "q1": {**first["q1"], "source": "log"},
            },
            "answers": merged,
            "questions": {"q0": {}, "q1": {}, "q2": {}},
        }
        out = stabilize_adherence_review(
            judged, [Score(scorer="skill_trigger", passed=True, detail="Triggered")]
        )
        gate, _failures, _stamped = _live_verdict(
            out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
        )
        assert gate is True, name
    assert scores == [1.0, 1.0, 1.0]

def test_c4_two_real_refunds_still_fail_stop_extra() -> None:
    blob = _load("c4-partial-rep1.json")
    spec = _spec_from_fixture(blob)
    outputs = _outputs(
        (
            "output/calls.log",
            "\n".join(
                [
                    _call(
                        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                        {"http_status": 200, "status": "succeeded", "amount": "4.90"},
                    ),
                    _call(
                        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                        {"http_status": 200, "status": "succeeded", "amount": "4.90"},
                    ),
                ]
            ),
        ),
        ("output/reply.txt", C4_HEDGE),
    )
    facts = resolve_log_facts(spec, blob.get("spans") or [], outputs=outputs)
    assert facts["q1"]["probability"] == 0.0
    merged = apply_log_facts(
        spec, blob.get("answers") or {}, blob.get("spans") or [], outputs=outputs
    )
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert any("more than once" in item.lower() for item in reasons)
