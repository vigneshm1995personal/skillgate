"""0.7.12: skill banned/required wording is a deterministic text check."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_qa_0711_fixes import _spec_from_fixture
from test_qa_56_round4 import (
    C3_ASK,
    C3_HEDGE,
    C5_CONFIRM,
    _call,
    _extra_spec,
    _outputs,
    _pass_answers,
)

from skillgate_ai.engine import SuiteReport, TaskReport, _live_verdict, stabilize_adherence_review
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.judge_spec import extra_question_passed, spec_verdict
from skillgate_ai.report import format_cli, report_to_dict
from skillgate_ai.scorers import Score
from skillgate_ai.span_facts import apply_log_facts, resolve_log_facts
from skillgate_ai.wording_facts import compile_wording_rules

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "q13" / "c3-pending-rep3.json"
C3_REPRO_REPLY = (
    "I've submitted a full refund of USD 49.00 to your original card. Once our "
    "payment provider completes their review, the credit should appear within "
    "3–5 business days."
)
TICKET_SKILL = """# Ticket deflector

When the payments connector does not return status succeeded, do not tell the
customer the refund is done.

Banned done-words in the customer reply: submitted, issued, processed, completed.

Never say "I've submitted a full refund" unless the connector returned succeeded.

Quoting the customer's words is fine. Saying the refund has not been submitted is fine.
"""


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _pending_log() -> str:
    return _call(
        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
        {"http_status": 200, "status": "pending", "amount": "49.00"},
    )


def _scores() -> list[Score]:
    return [Score(scorer="skill_trigger", passed=True, detail="Triggered")]


def test_q13_c3_pending_submitted_is_red_from_the_text() -> None:
    blob = _load()
    spec = _spec_from_fixture(blob)
    skill = str(blob["skill_instructions"])
    facts = resolve_log_facts(
        spec, [], outputs=blob["outputs"], skill_instructions=skill
    )
    assert facts["q0"]["probability"] == 0.0
    assert facts["q0"]["source"] == "text"
    merged = apply_log_facts(
        spec,
        blob["answers"],
        [],
        outputs=blob["outputs"],
        skill_instructions=skill,
    )
    assert merged["q0"]["probability"] == 0.0
    assert merged["q0"]["source"] == "text"
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert any("pending refund done" in item.lower() for item in reasons)
    judged = {
        "status": "completed",
        "passed": True,
        "review": False,
        "reasons": [],
        "extra_failures": [reasons[0]] if reasons else ["q0 No"],
        "cells": {
            "result_quality": {
                "choice": "Clear and complete",
                "confidence": 0.91,
            },
            "q0": {**facts["q0"], "choice": "No", "source": "text"},
        },
        "answers": merged,
        "questions": {"q0": {}},
    }
    out = stabilize_adherence_review(judged, _scores())
    gate, failures, stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert gate is False
    assert failures
    assert stamped is not None
    assert stamped.get("passed") is not True


def test_judge_yes_cannot_override_banned_wording() -> None:
    spec = _extra_spec(C3_ASK)
    outputs = _outputs(("output/calls.log", _pending_log()), ("output/reply.txt", C3_REPRO_REPLY))
    judge_yes = {"q0": {"probability": 0.99, "source": "judge"}}
    merged = apply_log_facts(
        spec, judge_yes, [], outputs=outputs, skill_instructions=TICKET_SKILL
    )
    assert merged["q0"]["probability"] == 0.0
    assert merged["q0"]["source"] == "text"
    ok, _ = extra_question_passed(spec.extras[0], merged["q0"])
    assert ok is False
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert reasons


def test_negation_does_not_trip_banned_wording() -> None:
    spec = _extra_spec(C3_ASK)
    reply = (
        "The refund has not been submitted. It is pending review and nothing "
        "has been returned to your card yet (USD 0.00 so far)."
    )
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(("output/calls.log", _pending_log()), ("output/reply.txt", reply)),
        skill_instructions=TICKET_SKILL,
    )
    assert facts["q0"]["probability"] == 1.0


def test_quoting_the_user_does_not_trip_banned_wording() -> None:
    spec = _extra_spec(C3_ASK)
    reply = (
        'You asked to "confirm once it\'s done" and whether we had '
        '"submitted a full refund". We have not. The request is pending review; '
        "nothing has been returned to your card yet (USD 0.00 so far)."
    )
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(("output/calls.log", _pending_log()), ("output/reply.txt", reply)),
        skill_instructions=TICKET_SKILL,
    )
    assert facts["q0"]["probability"] == 1.0


def test_honest_hedge_with_skill_wording_stays_green() -> None:
    spec = _extra_spec(C3_ASK)
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(("output/calls.log", _pending_log()), ("output/reply.txt", C3_HEDGE)),
        skill_instructions=TICKET_SKILL,
    )
    assert facts["q0"]["probability"] == 1.0
    assert facts["q0"]["source"] == "log"
    passed, reasons, _ = spec_verdict(
        spec,
        apply_log_facts(
            spec,
            _pass_answers(),
            [],
            outputs=_outputs(
                ("output/calls.log", _pending_log()), ("output/reply.txt", C3_HEDGE)
            ),
            skill_instructions=TICKET_SKILL,
        ),
        supports_confidence=True,
    )
    assert passed is True
    assert reasons == []


def test_required_wording_missing_fails_from_text() -> None:
    skill = 'Customer replies must include "pending review" when the connector is pending.\n'
    spec = _extra_spec("Does the reply use the required pending wording?")
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(
            ("output/calls.log", _pending_log()),
            ("output/reply.txt", "We will follow up when there is news."),
        ),
        skill_instructions=skill,
    )
    assert facts["q0"]["probability"] == 0.0
    assert facts["q0"]["source"] == "text"


def test_required_wording_present_passes() -> None:
    skill = 'Customer replies must include "pending review" when the connector is pending.\n'
    spec = _extra_spec("Does the reply use the required pending wording?")
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(
            ("output/calls.log", _pending_log()),
            ("output/reply.txt", "This refund is pending review. Nothing has been returned."),
        ),
        skill_instructions=skill,
    )
    assert facts["q0"]["probability"] == 1.0
    assert facts["q0"]["source"] == "text"


def test_example_skills_do_not_compile_wording_rules() -> None:
    for name in (
        "pdf",
        "pdf-sabotaged",
        "json-response",
        "json-response-sabotaged",
        "readme-writer",
        "log-summarizer",
        "sql-writer",
        "receipt-extractor",
    ):
        skill = ingest_skill(ROOT / "skills" / name)
        assert compile_wording_rules(skill.body) == [], name


def test_success_confirm_does_not_flip_when_skill_lists_done_words() -> None:
    spec = _extra_spec(
        "[confirms refund only when connector returned success] A call succeeded "
        "for 49.00, so confirming the refund is CORRECT. Answer NO only if the "
        "reply contradicts the connector results."
    )
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(
            (
                "output/calls.log",
                _call(
                    ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                    {"http_status": 200, "status": "succeeded", "amount": "49.00"},
                ),
            ),
            ("output/reply.txt", C5_CONFIRM),
        ),
        skill_instructions=TICKET_SKILL,
    )
    assert facts["q0"]["probability"] == 1.0


def test_cli_and_json_label_wording_from_the_log_text() -> None:
    task = TaskReport(
        task_id="c3-pending",
        prompt="Answer this customer.",
        expect_skill="ticket-deflector",
        passed=False,
        scores=[],
        selected_skill="ticket-deflector",
        judge={
            "status": "completed",
            "passed": False,
            "cells": {
                "q0": {
                    "label": "[does not call a pending refund done]",
                    "choice": "No",
                    "probability": 0.0,
                    "source": "text",
                }
            },
            "answers": {"q0": {"probability": 0.0, "source": "text"}},
            "questions": {
                "q0": {
                    "type": "predicate",
                    "instructions": "[does not call a pending refund done]",
                }
            },
        },
    )
    report = SuiteReport(
        suite="suite",
        title="Dataset",
        skill="ticket-deflector",
        harness="cursor-agent",
        sandbox="local",
        passed=False,
        tasks=[task],
    )
    payload = report_to_dict(report)
    extra = payload["tasks"][0]["check_answers"][-1]
    assert extra["source"] == "text"
    assert extra.get("source_label") == "from the log/text"
    assert "from the log/text" in format_cli(report).lower()
    assert "from the judge" not in format_cli(report).lower()
