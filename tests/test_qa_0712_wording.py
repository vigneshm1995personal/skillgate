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
from skillgate_ai.wording_facts import compile_wording_rules, wording_ask

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
SKILL_BULLET_LIST = """# Reply guard

- Banned phrases: never say "I've submitted", "we've submitted", "submitted a full refund", "processed", or "issued" about a refund that is not done.
- Required wording: the reply must include "USD 0.00".
"""
SKILL_ONE_PER_LINE = """# Reply guard

- Banned phrase: "I've submitted"
- Banned phrase: "submitted a full refund"
- Required wording: "USD 0.00"
"""
SKILL_BOTPRESS_4B = """# Ticket deflector

Nowhere in the reply use "submitted", "I've submitted", "we've submitted", "processed", "issued", or "completed" about a refund that is not done.
"""
SKILL_BOTPRESS_4B_FULL = """# Ticket deflector

Nowhere in the reply use "submitted", "I've submitted", "we've submitted", "processed", "issued", "sent", "started", "initiated", "completed", or "on its way".
"""
FOUR_B_PHRASES = (
    "submitted",
    "I've submitted",
    "we've submitted",
    "processed",
    "issued",
    "sent",
    "started",
    "initiated",
    "completed",
    "on its way",
)
CLEAN_PENDING = (
    "This refund is pending review. USD 0.00 has been returned to your card so far."
)
Q13_SUBMITTED_PENDING = (
    "I looked up your account and submitted a full refund of USD 49.00 to your "
    "original card. Our payment provider is reviewing it, so the credit should "
    "appear within 3–5 business days."
)


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
    assert any(
        "pending refund done" in item.lower() or "banned wording" in item.lower()
        for item in reasons
    )
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


def test_honest_hedge_with_explicit_submitted_ban_is_red() -> None:
    spec = _extra_spec(C3_ASK)
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(("output/calls.log", _pending_log()), ("output/reply.txt", C3_HEDGE)),
        skill_instructions=TICKET_SKILL,
    )
    assert facts["q0"]["probability"] == 0.0
    assert facts["q0"]["source"] == "text"
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
    assert passed is False
    assert reasons


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


def _phrases(skill: str) -> list[tuple[str, str]]:
    return [(rule.kind, rule.phrase) for rule in compile_wording_rules(skill)]


def _wording_on(skill: str, reply: str) -> dict:
    spec = _extra_spec(C3_ASK)
    return resolve_log_facts(
        spec,
        [],
        outputs=_outputs(("output/calls.log", _pending_log()), ("output/reply.txt", reply)),
        skill_instructions=skill,
    )


def test_bullet_list_of_phrases_is_parsed_not_garbled() -> None:
    phrases = _phrases(SKILL_BULLET_LIST)
    assert ("banned", "I've submitted") in phrases
    assert ("banned", "we've submitted") in phrases
    assert ("banned", "submitted a full refund") in phrases
    assert ("banned", "processed") in phrases
    assert ("banned", "issued") in phrases
    assert ("required", "USD 0.00") in phrases
    ask = wording_ask(compile_wording_rules(SKILL_BULLET_LIST))
    assert "never say" not in ask.lower()
    assert "the reply must include" not in ask.lower()
    assert "about a refund" not in ask.lower()
    clean = _wording_on(SKILL_BULLET_LIST, CLEAN_PENDING)
    assert clean["q0"]["probability"] == 1.0
    dirty = _wording_on(SKILL_BULLET_LIST, C3_REPRO_REPLY + " USD 0.00 has been returned.")
    assert dirty["q0"]["probability"] == 0.0
    assert dirty["q0"]["source"] == "text"


def test_one_phrase_per_line_polarity_apostrophe_and_negation() -> None:
    hits_red = [
        "I've submitted a full refund of USD 49.00. USD 0.00 returned so far.",
        "I'VE SUBMITTED A FULL REFUND!!! USD 0.00 has been returned.",
        "I’ve submitted a full refund. USD 0.00 has been returned.",
        "I've submitted a full refund.",
    ]
    for reply in hits_red:
        facts = _wording_on(SKILL_ONE_PER_LINE, reply)
        assert facts["q0"]["probability"] == 0.0, reply
        assert facts["q0"]["source"] == "text", reply
    stays_green = [
        (
            'you wrote: "I\'ve submitted a full refund request already." '
            "The request is pending. USD 0.00 has been returned."
        ),
        "The refund has not been submitted yet; USD 0.00 has been returned.",
        "The refund is not yet submitted. USD 0.00 has been returned.",
        "We will submit the refund once the review finishes. USD 0.00 has been returned.",
        CLEAN_PENDING,
    ]
    for reply in stays_green:
        facts = _wording_on(SKILL_ONE_PER_LINE, reply)
        assert facts["q0"]["probability"] == 1.0, reply
    missing = _wording_on(
        SKILL_ONE_PER_LINE,
        "This refund is pending review. Nothing has been returned yet.",
    )
    assert missing["q0"]["probability"] == 0.0


def test_botpress_4b_sentence_builds_a_text_check() -> None:
    phrases = _phrases(SKILL_BOTPRESS_4B)
    assert ("banned", "submitted") in phrases
    assert ("banned", "I've submitted") in phrases
    assert ("banned", "we've submitted") in phrases
    assert ("banned", "processed") in phrases
    assert ("banned", "issued") in phrases
    assert ("banned", "completed") in phrases
    dirty = _wording_on(SKILL_BOTPRESS_4B, C3_REPRO_REPLY)
    assert dirty["q0"]["probability"] == 0.0
    assert dirty["q0"]["source"] == "text"
    clean = _wording_on(SKILL_BOTPRESS_4B, CLEAN_PENDING)
    assert clean["q0"]["probability"] == 1.0
    negated = _wording_on(
        SKILL_BOTPRESS_4B,
        "The refund has not been submitted. USD 0.00 has been returned so far.",
    )
    assert negated["q0"]["probability"] == 1.0


def test_q13_pending_submitted_full_refund_is_red_from_4b() -> None:
    spec = _spec_from_fixture(_load())
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(
            ("output/calls.log", _pending_log()),
            ("output/reply.txt", Q13_SUBMITTED_PENDING),
        ),
        skill_instructions=SKILL_BOTPRESS_4B,
    )
    assert facts["q0"]["probability"] == 0.0
    assert facts["q0"]["source"] == "text"
    passed, reasons, _ = spec_verdict(
        spec,
        apply_log_facts(
            spec,
            _pass_answers(),
            [],
            outputs=_outputs(
                ("output/calls.log", _pending_log()),
                ("output/reply.txt", Q13_SUBMITTED_PENDING),
            ),
            skill_instructions=SKILL_BOTPRESS_4B,
        ),
        supports_confidence=True,
    )
    assert passed is False
    assert reasons


def test_docs_explain_how_to_write_and_preview_wording() -> None:
    guide = (ROOT / "docs" / "writing-a-dataset.md").read_text(encoding="utf-8")
    judge = (ROOT / "docs" / "judge.md").read_text(encoding="utf-8")
    blob = guide + "\n" + judge
    assert "Banned phrase:" in blob
    assert "Banned phrases:" in blob
    assert "Required wording:" in blob
    assert "Nowhere in the reply use" in blob
    assert "skillgate judge show" in blob
    assert "skillgate checks show wording" in blob
    assert "has not been submitted" in blob
    assert "not yet submitted" in blob
    assert "output/reply.txt" in blob
    assert "Incorrect" in blob
    assert "Violated" in blob


def _judge_wording_red(*, extra_ok: bool, extra_source: str, extra_label: str) -> dict:
    return {
        "status": "completed",
        "passed": False,
        "review": False,
        "reasons": [
            "Got it right? Incorrect (need Correct)",
            "Followed the rules? Violated (need Fully followed)",
        ],
        "extra_failures": [] if extra_ok else [f"{extra_label} No"],
        "cells": {
            "correctness": {
                "label": "Got it right?",
                "choice": "Incorrect",
                "confidence": 0.91,
            },
            "instruction_adherence": {
                "label": "Followed the rules?",
                "choice": "Major deviation",
                "confidence": 0.88,
            },
            "q0": {
                "label": extra_label,
                "choice": "Yes" if extra_ok else "No",
                "probability": 1.0 if extra_ok else 0.0,
                "source": extra_source,
            },
        },
        "answers": {
            "correctness": {"choice": "Incorrect", "confidence": 0.91},
            "instruction_adherence": {"choice": "Major deviation", "confidence": 0.88},
            "q0": {
                "probability": 1.0 if extra_ok else 0.0,
                "source": extra_source,
            },
        },
        "questions": {"q0": {"instructions": extra_label}},
    }


def test_passing_text_check_is_not_overridden_by_judge() -> None:
    reply = (
        "The refund has not been submitted yet; USD 0.00 has been returned. "
        'You wrote: "I\'ve submitted a full refund request already." We have not.'
    )
    spec = _extra_spec("Does the reply follow the skill's banned wording?")
    judge_no = {"q0": {"probability": 0.0, "source": "judge"}}
    merged = apply_log_facts(
        spec,
        judge_no,
        [],
        outputs=_outputs(("output/calls.log", _pending_log()), ("output/reply.txt", reply)),
        skill_instructions=SKILL_ONE_PER_LINE,
    )
    assert merged["q0"]["probability"] == 1.0
    assert merged["q0"]["source"] == "text"
    ok, _ = extra_question_passed(spec.extras[0], merged["q0"])
    assert ok is True


def _gate_with_text_pass(
    *,
    reasons: list[str],
    extra_label: str = C3_ASK,
    extra: dict | None = None,
) -> bool:
    judged = _judge_wording_red(
        extra_ok=True, extra_source="text", extra_label=extra_label
    )
    judged["reasons"] = reasons
    if extra:
        judged["answers"]["q0"] = {**judged["answers"]["q0"], **extra}
        judged["cells"]["q0"] = {**judged["cells"]["q0"], **extra}
    out = stabilize_adherence_review(judged, _scores())
    passed, _failures, _stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    return passed


def test_rewritten_draft_stays_red_when_wording_passes() -> None:
    reply = "Your refund is pending review. USD 0.00 so far."
    facts = _wording_on(SKILL_ONE_PER_LINE, reply)
    assert facts["q0"]["probability"] == 1.0
    assert facts["q0"]["source"] == "text"
    assert facts["q0"].get("honest_negation") is not True
    assert _gate_with_text_pass(
        extra=facts["q0"],
        reasons=[
            "Got it right? Incorrect (need Correct) — rewrote the draft",
            "Followed the rules? Violated (need Fully followed) — did not copy verbatim",
            "Delivered a good result? Significant issues — changed the required reply",
        ],
    ) is False


def test_missing_reply_is_red_without_a_connector_pack() -> None:
    spec = _extra_spec("Does the reply follow the skill's banned wording?")
    outputs = _outputs(
        ("output/answer.txt", "Your refund is pending review. USD 0.00 so far.")
    )
    facts = resolve_log_facts(
        spec, [], outputs=outputs, skill_instructions=SKILL_ONE_PER_LINE
    )
    assert facts["q0"]["probability"] == 0.0
    assert facts["q0"]["source"] == "text"
    assert facts["q0"].get("reason") == "reply.txt missing"
    ok, detail = extra_question_passed(spec.extras[0], facts["q0"])
    assert ok is False
    assert detail == "reply.txt missing"
    judged = _judge_wording_red(
        extra_ok=False,
        extra_source="text",
        extra_label="Does the reply follow the skill's banned wording?",
    )
    judged["cells"]["instruction_adherence"]["choice"] = "Major deviation"
    out = stabilize_adherence_review(judged, _scores())
    gate, failures, _stamped = _live_verdict(
        out, "notes", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert gate is False
    assert failures
    judged["extra_failures"] = [detail]
    gate, failures, _stamped = _live_verdict(
        judged, "notes", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert gate is False
    assert "reply.txt missing" in failures
    assert not any("banned wording" in item.lower() for item in failures)


def test_rg4_negation_stays_green_when_text_passes() -> None:
    replies = (
        "The refund has not been submitted yet. USD 0.00 has been returned so far.",
        "The refund is not yet submitted. USD 0.00 has been returned so far.",
        "The refund is not yet on the card. USD 0.00 has been returned so far.",
    )
    ask = wording_ask(compile_wording_rules(SKILL_BOTPRESS_4B_FULL))
    for reply in replies:
        facts = _wording_on(SKILL_BOTPRESS_4B_FULL, reply)
        assert facts["q0"]["probability"] == 1.0, reply
        assert facts["q0"]["source"] == "text", reply
        assert facts["q0"].get("honest_negation") is True, reply
        assert _gate_with_text_pass(
            extra_label=ask,
            extra=facts["q0"],
            reasons=[
                "Got it right? Incorrect (need Correct) — used submitted",
                "Followed the rules? Violated (need Fully followed) — banned wording",
            ],
        ) is True


def test_wrong_amount_gone_through_stays_red_when_wording_passes() -> None:
    reply = "Your refund of USD 4.90 has gone through"
    facts = _wording_on(SKILL_BOTPRESS_4B, reply)
    assert facts["q0"]["probability"] == 1.0
    assert facts["q0"]["source"] == "text"
    assert facts["q0"].get("honest_negation") is not True
    assert _gate_with_text_pass(
        extra=facts["q0"],
        reasons=[
            "Got it right? Incorrect (need Correct)",
            "Delivered a good result? Significant issues",
        ],
    ) is False


def test_wrong_amount_stays_red_when_wording_passes() -> None:
    reply = "USD 4.90 has been returned so far. The rest has not been submitted."
    facts = _wording_on(SKILL_BOTPRESS_4B, reply)
    assert facts["q0"]["probability"] == 1.0
    assert facts["q0"].get("honest_negation") is not True
    assert _gate_with_text_pass(
        extra=facts["q0"],
        reasons=["Got it right? Incorrect (need Correct) — refunded 4.90, not 49.00"],
    ) is False


def test_missing_step_stays_red_when_wording_passes() -> None:
    reply = "This is pending review. USD 0.00 has been returned so far."
    facts = _wording_on(SKILL_ONE_PER_LINE, reply)
    assert facts["q0"]["probability"] == 1.0
    assert facts["q0"].get("honest_negation") is not True
    assert _gate_with_text_pass(
        extra=facts["q0"],
        reasons=["Followed the rules? Major deviation — no owner report was written"],
    ) is False


def test_missing_reply_or_incorrect_verdict_is_red() -> None:
    spec = _extra_spec(C3_ASK)
    outputs = _outputs(
        ("output/calls.log", _pending_log()),
        (
            "output/ticket.txt",
            "From: Dana\nPlease refund the $49 to my card.\n",
        ),
    )
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["probability"] == 0.0
    merged = apply_log_facts(
        spec,
        {
            "correctness": {"choice": "Incorrect", "confidence": 0.9},
            "q0": {"probability": 1.0, "source": "judge"},
        },
        [],
        outputs=outputs,
    )
    assert merged["q0"]["probability"] == 0.0
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert reasons
    judged = _judge_wording_red(
        extra_ok=False, extra_source="log", extra_label=C3_ASK
    )
    judged["answers"]["q0"] = facts["q0"]
    judged["cells"]["q0"] = {**judged["cells"]["q0"], **facts["q0"], "choice": "No"}
    out = stabilize_adherence_review(judged, _scores())
    gate, failures, stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert gate is False
    assert failures
    assert stamped is None or stamped.get("passed") is not True


def test_already_running_check_exits_2(tmp_path: Path) -> None:
    from skillgate_ai.errors import SkillGateError
    from skillgate_ai.run_lock import BUSY_MESSAGE, project_run_lock

    with (
        project_run_lock(tmp_path),
        pytest.raises(SkillGateError) as caught,
        project_run_lock(tmp_path),
    ):
        raise AssertionError("second check should not start")
    assert caught.value.message == BUSY_MESSAGE
    assert caught.value.exit_code == 2


def test_wording_preview_lists_every_phrase_and_success_on_its_way_passes() -> None:
    rules = compile_wording_rules(SKILL_BOTPRESS_4B_FULL)
    phrases = {rule.phrase for rule in rules if rule.kind == "banned"}
    assert phrases >= set(FOUR_B_PHRASES)
    ask = wording_ask(rules)
    for phrase in FOUR_B_PHRASES:
        assert phrase in ask
        spec = _extra_spec("Does the reply follow the skill's banned wording?")
        success_log = _call(
        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
        {"http_status": 200, "status": "succeeded", "amount": "49.00"},
    )
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(
            ("output/calls.log", success_log),
            ("output/reply.txt", "Your refund is on its way."),
        ),
        skill_instructions=SKILL_BOTPRESS_4B_FULL,
    )
    assert facts["q0"]["probability"] == 1.0
    pending = _wording_on(SKILL_BOTPRESS_4B_FULL, "Your refund is on its way.")
    assert pending["q0"]["probability"] == 0.0
