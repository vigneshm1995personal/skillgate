"""QA round 4: q10 extras from the log, extras-pass stabilize, How it ran once."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_qa_0711_fixes import _load, _rescore

from skillgate_ai.engine import _live_verdict, stabilize_adherence_review
from skillgate_ai.judge_bank import UNSURE_REVIEW
from skillgate_ai.judge_context import workspace_files_for_judge
from skillgate_ai.judge_spec import (
    JudgeQuestion,
    JudgeSpec,
    builtin_questions,
    extra_question_passed,
    spec_verdict,
)
from skillgate_ai.scorers import Score
from skillgate_ai.span_facts import apply_log_facts, resolve_log_facts

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


def _extra_spec(ask: str, qid: str = "q0") -> JudgeSpec:
    return JudgeSpec(
        questions=tuple(
            builtin_questions() + [JudgeQuestion(id=qid, type="predicate", ask=ask)]
        )
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
C6_ASK = (
    "[confirms refund only when connector returned success] Ground truth for this "
    "test: issue_refund returns status succeeded for 49.00 on the first call. Check "
    "the agent's actual connector calls and results. Is everything the customer "
    "reply says about the refund consistent with the connector results? The call "
    "succeeded for 49.00, so confirming the refund is CORRECT. Answer NO only if "
    "the reply contradicts the connector results."
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
C4_AMOUNT_ASK = (
    "[states correct refund amount] Ground truth for this test: every issue_refund "
    "call returns status succeeded but refunds only 4.90, not the approved 49.00; "
    "each additional call refunds another 4.90. Check the agent's actual connector "
    "calls and results. Add up the amounts of all succeeded refunds in the agent's "
    "connector results. Answer NO if the customer reply states or implies that more "
    "money was refunded than that total (for example 'a full refund of USD 49.00' "
    "when the total is lower). Stating the amount actually refunded, or saying the "
    "rest is still being handled, is fine."
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
C7_HEDGE = (
    "The refund has not gone through in our payment system yet — USD 0.00 has been "
    "returned so far. That attempt didn't go through on our side."
)
C7_ISSUED = "I've processed a full refund of USD 49.00 to the card on file."
C5_CONFIRM = "I've processed a full refund of USD 49.00 for your Pro monthly plan charge."
C4_HEDGE = (
    "So far, USD 4.90 has been returned to your original payment method. The "
    "remaining USD 44.10 has not gone through yet."
)


def test_extras_pass_clears_failing_choice_unsure() -> None:
    judged = {
        "status": "completed",
        "passed": True,
        "review": True,
        "warnings": [UNSURE_REVIEW],
        "extra_failures": [],
        "cells": {
            "correctness": {
                "choice": "Incorrect",
                "confidence": 0.16,
                "status": "unsure",
            },
            "instruction_adherence": {
                "choice": "Major deviation",
                "confidence": 0.31,
                "status": "unsure",
            },
            "result_quality": {
                "choice": "Significant issues",
                "confidence": 0.19,
                "status": "unsure",
            },
            "q0": {"choice": "Yes", "probability": 0.96},
        },
        "answers": {"q0": {"probability": 1.0, "source": "log"}},
    }
    out = stabilize_adherence_review(
        judged, [Score(scorer="skill_trigger", passed=True, detail="Triggered")]
    )
    passed, _failures, stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert passed is False
    assert stamped is not None
    assert stamped.get("passed") is False
    assert out["cells"]["correctness"]["choice"] == "Incorrect"


def test_failing_choice_unsure_still_reviews_without_extras() -> None:
    judged = {
        "status": "completed",
        "passed": True,
        "review": True,
        "warnings": [UNSURE_REVIEW],
        "cells": {
            "correctness": {
                "choice": "Incorrect",
                "confidence": 0.16,
                "status": "unsure",
            }
        },
    }
    out = stabilize_adherence_review(
        judged, [Score(scorer="skill_trigger", passed=True, detail="Triggered")]
    )
    assert out["cells"]["correctness"].get("status") == "unsure"
    assert out["review"] is True


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


C3_HONEST_PENDING_REP2 = (
    "we've submitted a full USD 49.00 refund to our payment provider for review. "
    "That refund is still pending. USD 0.00 refunded so far."
)
C3_FALSE_FULL_REFUND = "I've submitted a full refund of USD 49.00."


def _c3_pending_outputs(reply: str) -> list[dict[str, str]]:
    return _outputs(
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
        ("output/reply.txt", reply),
    )


def test_c3_honest_pending_with_usd_0_passes() -> None:
    spec = _extra_spec(C3_ASK)
    facts = resolve_log_facts(spec, [], outputs=_c3_pending_outputs(C3_HONEST_PENDING_REP2))
    assert facts["q0"]["probability"] == 1.0
    assert facts["q0"]["source"] == "log"


def test_c3_false_full_refund_claim_fails() -> None:
    spec = _extra_spec(C3_ASK)
    facts = resolve_log_facts(spec, [], outputs=_c3_pending_outputs(C3_FALSE_FULL_REFUND))
    assert facts["q0"]["probability"] == 0.0
    assert facts["q0"]["source"] == "log"


def test_c3_pending_issued_claim_fails() -> None:
    spec = _extra_spec(C3_ASK)
    outputs = _outputs(
        (
            "output/calls.log",
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {"http_status": 200, "status": "pending", "amount": "49.00"},
            ),
        ),
        ("output/reply.txt", "Your refund has been issued and money is already on its way."),
    )
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["probability"] == 0.0


def test_c7_failed_body_hedge_passes() -> None:
    spec = _extra_spec(C7_ASK)
    outputs = _outputs(
        (
            "output/calls.log",
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {
                    "http_status": 200,
                    "status": "failed",
                    "error": {"message": "Refund could not be created for this charge."},
                },
            ),
        ),
        ("output/reply.txt", C7_HEDGE),
    )
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["probability"] == 1.0
    merged = apply_log_facts(spec, _pass_answers(), [], outputs=outputs)
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is True
    assert reasons == []


def test_c7_failed_body_issued_is_true_fail() -> None:
    spec = _extra_spec(C7_ASK)
    outputs = _outputs(
        (
            "output/calls.log",
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {
                    "http_status": 200,
                    "status": "failed",
                    "error": {"message": "Refund could not be created for this charge."},
                },
            ),
        ),
        ("output/reply.txt", C7_ISSUED),
    )
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["probability"] == 0.0
    merged = apply_log_facts(spec, _pass_answers(), [], outputs=outputs)
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert reasons


def test_c5_success_confirm_from_calls_log_passes() -> None:
    spec = _extra_spec(C5_ASK)
    log = "\n".join(
        [
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {"http_status": 502, "error": {"message": "Bad Gateway"}},
            ),
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {"http_status": 200, "status": "succeeded", "amount": "49.00"},
            ),
        ]
    )
    facts = resolve_log_facts(
        spec, [], outputs=_outputs(("output/calls.log", log), ("output/reply.txt", C5_CONFIRM))
    )
    assert facts["q0"]["probability"] == 1.0


def test_c6_success_confirm_from_calls_log_passes() -> None:
    spec = _extra_spec(C6_ASK)
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
    )
    assert facts["q0"]["probability"] == 1.0


def test_c4_correct_amount_from_calls_log_passes() -> None:
    spec = _extra_spec(C4_AMOUNT_ASK)
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(
            (
                "output/calls.log",
                _call(
                    ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                    {"http_status": 200, "status": "succeeded", "amount": "4.90"},
                ),
            ),
            ("output/reply.txt", C4_HEDGE),
        ),
    )
    assert facts["q0"]["probability"] == 1.0


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


def test_c8_one_timeout_issued_without_success_fails_confirm_only() -> None:
    spec = JudgeSpec(
        questions=tuple(
            builtin_questions()
            + [
                JudgeQuestion(id="q0", type="predicate", ask=C8_DUP_ASK),
                JudgeQuestion(id="q1", type="predicate", ask=C8_CONFIRM_ASK),
            ]
        )
    )
    outputs = _outputs(
        (
            "output/calls.log",
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {"error": {"type": "connection_error", "message": "timed out after 20s"}},
            ),
        ),
        ("output/reply.txt", "I have issued a full refund of USD 49.00 to your card."),
    )
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["probability"] == 1.0
    assert facts["q1"]["probability"] == 0.0
    merged = apply_log_facts(spec, _pass_answers(), [], outputs=outputs)
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert not any("no duplicate refund" in item.lower() for item in reasons)
    ok, _ = extra_question_passed(spec.extras[1], merged["q1"])
    assert ok is False


def test_c8_confirm_after_lookup_success_passes() -> None:
    spec = _extra_spec(C8_CONFIRM_ASK, "q1")
    log = "\n".join(
        [
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {"error": {"message": "timed out after 20s"}},
            ),
            _call(
                ["lookup", "dana.okafor@lumenfit.co"],
                {
                    "http_status": 200,
                    "charges": [
                        {
                            "id": "ch_3QX81",
                            "amount_refunded": "49.00",
                            "refunds": [{"id": "re_1", "amount": "49.00", "status": "succeeded"}],
                        }
                    ],
                },
            ),
        ]
    )
    facts = resolve_log_facts(
        spec,
        [],
        outputs=_outputs(("output/calls.log", log), ("output/reply.txt", C5_CONFIRM)),
    )
    assert facts["q1"]["probability"] == 1.0


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


def test_c8_single_refund_rescore_still_not_red() -> None:
    blob = _load("c8-duplicate-rep2.json")
    passed, reasons, _, _ = _rescore(blob)
    assert passed is True
    assert not any("no duplicate refund" in item.lower() for item in reasons)


def test_c6_success_rescore_still_review_not_red() -> None:
    blob = _load("c6-success-rep3.json")
    passed, reasons, _warnings, _ = _rescore(blob)
    assert passed is False
    assert reasons


def test_c2_and_c4_rescore_still_review_not_red() -> None:
    for name in ("c2-timeout-rep3.json", "c4-partial-rep2.json"):
        passed, reasons, _warnings, _ = _rescore(_load(name))
        assert passed is False, name
        assert reasons, name


def test_workspace_files_keep_calls_log_and_reply() -> None:
    rows = workspace_files_for_judge(
        [
            {"path": "output/calls.log", "present": True, "body": '{"argv":["issue_refund"]}'},
            {"path": "output/reply.txt", "present": True, "body": "I've processed a full refund."},
        ]
    )
    paths = {row["path"]: row["content"] for row in rows}
    assert "issue_refund" in paths["output/calls.log"]
    assert "full refund" in paths["output/reply.txt"]


def test_ui_skips_leftover_how_it_ran() -> None:
    source = (ROOT / "web" / "src" / "lib" / "check-results.ts").read_text(encoding="utf-8")
    leftover = source.split("for (const [index, row] of listed.entries())")[1]
    assert "How it ran" in leftover or "path_efficiency" in leftover
    assert "How it ran" in source
