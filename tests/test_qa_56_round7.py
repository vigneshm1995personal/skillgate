"""QA round 7: F12 c4 amount extras are deterministic from the same log."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_qa_0711_fixes import _load, _spec_from_fixture
from test_qa_56_round4 import C4_HEDGE, _call, _outputs

from skillgate_ai.engine import _live_verdict, stabilize_adherence_review
from skillgate_ai.scorers import Score
from skillgate_ai.span_facts import apply_log_facts, resolve_log_facts
from skillgate_ai.judge_spec import spec_verdict

ROOT = Path(__file__).resolve().parents[1]
C4_FIXTURES = (
    "c4-partial-rep1.json",
    "c4-partial-rep2.json",
    "c4-partial-rep3.json",
)
C4_STOP_ASK = "[stops and escalates on a wrong refund amount]"


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


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
    merged = apply_log_facts(spec, blob.get("answers") or {}, blob.get("spans") or [], outputs=outputs)
    passed, reasons, _ = spec_verdict(spec, merged, supports_confidence=True)
    assert passed is False
    assert any("more than once" in item.lower() for item in reasons)


def test_readme_unstarted_or_timeout_is_not_scored() -> None:
    text = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    assert "not scored" in text
    assert "timed-out" in text or "timed out" in text
    assert "unstarted" in text
