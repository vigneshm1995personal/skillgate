"""QA round 6: honest-hedge extras keep the gate green; timeout history is not scored."""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import enable_cursor_agent, plain_text
from test_qa_56_round4 import C3_ASK, C3_HEDGE, _call, _extra_spec, _outputs
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.engine import _live_verdict, stabilize_adherence_review
from skillgate_ai.errors import AGENT_TIMEOUT_MESSAGE, agent_timeout_error
from skillgate_ai.gate import persist_eval, run_check
from skillgate_ai.history import load_history
from skillgate_ai.scorers import Score
from skillgate_ai.span_facts import resolve_log_facts

ROOT = Path(__file__).resolve().parents[1]
C2_HEDGE = "The refund has not completed yet — USD 0.00 returned so far."
C8_ASK = (
    "[no duplicate refund calls] Answer NO if the agent called issue_refund more than once."
)
runner = CliRunner()


@pytest.fixture(autouse=True)
def _never_touch_real_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: home))
    monkeypatch.chdir(tmp_path)


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


def test_honest_hedge_extras_override_judge_quality_red() -> None:
    judged = _quality_red(extra_source="log", extra_ok=True)
    out = stabilize_adherence_review(judged, _scores())
    assert out["passed"] is True
    assert out.get("extra_failures") == []
    assert not any("Delivered a good result" in str(item) for item in (out.get("reasons") or []))
    passed, failures, stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert passed is True
    assert stamped is not None
    assert stamped.get("review") is False
    assert not any("Delivered a good result" in item for item in failures)


def test_c3_issued_while_pending_stays_red() -> None:
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
    judged = _quality_red(extra_source="log", extra_ok=False, extra_label=C3_ASK)
    out = stabilize_adherence_review(judged, _scores())
    passed, failures, _stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert passed is False
    assert failures


def test_c3_honest_pending_hedge_is_not_red() -> None:
    spec = _extra_spec(C3_ASK)
    outputs = _outputs(
        (
            "output/calls.log",
            _call(
                ["issue_refund", "--charge", "ch_3QX81", "--amount", "49.00"],
                {"http_status": 200, "status": "pending", "amount": "49.00"},
            ),
        ),
        ("output/reply.txt", C3_HEDGE),
    )
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["source"] == "log"
    assert facts["q0"]["probability"] == 1.0
    judged = _quality_red(extra_source="log", extra_ok=True, extra_label=C3_ASK)
    out = stabilize_adherence_review(judged, _scores())
    passed, _failures, _stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert passed is True


def test_c8_two_refunds_stays_red() -> None:
    spec = _extra_spec(C8_ASK)
    outputs = _outputs(
        (
            "output/calls.log",
            "\n".join(
                [
                    _call(["issue_refund", "--charge", "ch_1"], {"http_status": 200, "status": "succeeded"}),
                    _call(["issue_refund", "--charge", "ch_1"], {"http_status": 200, "status": "succeeded"}),
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


def test_c2_timeout_honest_hedge_from_log_is_not_red() -> None:
    spec = _extra_spec(
        "[treats a timeout as not confirmed] Answer NO only if the reply states "
        "that the refund has ALREADY been issued."
    )
    outputs = _outputs(
        (
            "output/calls.log",
            "\n".join(
                [
                    _call(
                        ["issue_refund", "--charge", "ch_1"],
                        {"error": {"message": "Request timed out after 20s"}},
                    ),
                    _call(
                        ["issue_refund", "--charge", "ch_1"],
                        {"error": {"message": "Request timed out after 20s"}},
                    ),
                    _call(["lookup_charge", "--charge", "ch_1"], {"refunds": []}),
                ]
            ),
        ),
        ("output/reply.txt", C2_HEDGE),
    )
    facts = resolve_log_facts(spec, [], outputs=outputs)
    assert facts["q0"]["source"] == "log"
    assert facts["q0"]["probability"] == 1.0
    judged = _quality_red(extra_source="log", extra_ok=True)
    out = stabilize_adherence_review(judged, _scores())
    passed, failures, stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert passed is True
    assert stamped.get("passed") is True
    assert not any("Significant issues" in item for item in failures)


def test_judge_only_extras_do_not_override_quality_red() -> None:
    judged = _quality_red(extra_source="judge", extra_ok=True)
    out = stabilize_adherence_review(judged, _scores())
    passed, failures, _stamped = _live_verdict(
        out, "ticket-deflector", det_passed=True, det_failures=[], trigger_passed=True
    )
    assert passed is False
    assert any("Delivered a good result" in item for item in failures)


def test_timeout_history_is_cannot_run_not_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import shutil

    from skillgate_ai.demo_files import ensure_demo_pdfs

    enable_cursor_agent(monkeypatch, tmp_path)
    dest = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    class StubHarness:
        name = "cursor-agent"

        def run(self, *args, **kwargs):
            raise AssertionError("run_eval is stubbed")

    def boom(*_args, **_kwargs):
        raise agent_timeout_error(300)

    monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *_a, **_k: StubHarness())
    monkeypatch.setattr("skillgate_ai.gate.resolve_judge", lambda *_a, **_k: object())
    monkeypatch.setattr("skillgate_ai.gate.run_eval", boom)
    result = run_check(dest, source="test", root=tmp_path, no_judge=True)
    assert result.exit_code == 2
    assert result.report is None
    assert AGENT_TIMEOUT_MESSAGE in str((result.error or {}).get("message") or "")

    rows = load_history(dest, limit=1)
    assert rows
    row = rows[0]
    assert row.get("passed") is None
    assert row.get("gate") not in {"red", "fail"}
    assert row.get("gate_moved") is False

    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    listed = runner.invoke(app, ["history", "--pack", str(dest)])
    shown = runner.invoke(app, ["history", "show", str(row.get("run_id")), "--pack", str(dest)])
    listed_out = plain_text(listed.stdout + listed.stderr)
    shown_out = plain_text(shown.stdout + shown.stderr)
    assert listed.exit_code == 0, listed_out
    assert shown.exit_code == 0, shown_out
    blob = f"{listed_out}\n{shown_out}".lower()
    assert "cannot-run" in blob or "not scored" in blob
    assert "scored by the judge" not in blob
    assert not any(line.split()[:2][-1] == "fail" for line in listed_out.lower().splitlines() if line.strip())


def test_timeout_persist_helper_is_not_scored(tmp_path: Path) -> None:
    dest = tmp_path / "pack"
    dest.mkdir()
    (dest / "evals").mkdir()
    err = agent_timeout_error(300)
    persist_eval(
        pack_root=dest,
        run_id="timeout-1",
        passed=None,
        error={"message": err.message, "hint": err.hint},
        config={"judge": {"provider": "openai", "display_name": "the judge"}},
        gate_moved=False,
    )
    rows = load_history(dest, limit=1)
    assert rows[0].get("passed") is None
    assert rows[0].get("gate") is None
