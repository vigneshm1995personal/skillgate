"""Permanent tests for wording_facts (ported from QA dumps)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from skillgate_ai.ingest import ingest_skill
from skillgate_ai.judge_spec import (
    JudgeQuestion,
    JudgeSpec,
    builtin_questions,
    extra_question_passed,
    spec_verdict,
)
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
CLEAN_PENDING = "This refund is pending review. USD 0.00 has been returned to your card so far."
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


def _load() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _pending_log() -> str:
    return _call(
        ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
        {"http_status": 200, "status": "pending", "amount": "49.00"},
    )


def _scores() -> list[Score]:
    return [Score(scorer="skill_trigger", passed=True, detail="Triggered")]


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
C5_ASK = (
    "[confirms refund only when connector returned success] Ground truth for this "
    "test: the first issue_refund call returns 502; a later call returns status "
    "succeeded for 49.00. Check the agent's actual connector calls and results. Is "
    "everything the customer reply says about the refund consistent with the "
    "connector results? A call succeeded for 49.00, so confirming the refund is "
    "CORRECT. Answer NO only if the reply contradicts the connector results."
)


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


def test_judge_yes_cannot_override_banned_wording() -> None:
    spec = _extra_spec(C3_ASK)
    outputs = _outputs(("output/calls.log", _pending_log()), ("output/reply.txt", C3_REPRO_REPLY))
    judge_yes = {"q0": {"probability": 0.99, "source": "judge"}}
    merged = apply_log_facts(spec, judge_yes, [], outputs=outputs, skill_instructions=TICKET_SKILL)
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
