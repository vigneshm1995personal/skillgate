from __future__ import annotations

from pathlib import Path

from skillgate_ai.deploy_gate import (
    deploy_allowed,
    infer_gate_moved,
    local_gate,
    newest_gate_moving_row,
    pack_gate_decision,
    row_gate_moved,
    row_is_tryout,
    run_gate_decision,
    run_gate_summary,
)


def test_row_is_tryout_from_flag_and_report() -> None:
    assert row_is_tryout({"tryout": True}) is True
    assert row_is_tryout({"report": {"tryout": True}}) is True
    assert row_is_tryout({"passed": True}) is False


def test_infer_gate_moved_respects_tryout() -> None:
    assert infer_gate_moved(tryout=True, error=None, passed=False) is False
    assert infer_gate_moved(tryout=False, error=None, passed=True) is True


def test_run_gate_decision_blocked_on_failed_pass() -> None:
    row = {"passed": False, "tryout": False, "report": {"gate": "green"}}
    assert run_gate_decision(row) == ("blocked", "Get a passing run to unlock Deploy.")


def test_run_gate_summary_tryout_pending() -> None:
    summary = run_gate_summary({"tryout": True, "passed": True})
    assert summary["decision"] == "pending"
    assert "Single-check" in summary["reason"]


def test_newest_gate_moving_row_skips_non_moving() -> None:
    rows = [
        {"tryout": True, "passed": True},
        {"tryout": False, "passed": True, "report": {"gate": "green"}},
    ]
    picked = newest_gate_moving_row(rows)
    assert picked is rows[1]


def test_local_gate_error_does_not_move_gate() -> None:
    assert local_gate(None, status="error", tryout=False) == (
        "pending",
        "This run ended in error and did not change the gate.",
    )


def test_pack_gate_decision_empty_history(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "skillgate_ai.deploy_gate.load_history",
        lambda pack, limit=0: [],
    )
    assert pack_gate_decision(tmp_path) == ("pending", "Run checks to set the gate.")
    assert deploy_allowed(tmp_path) is False


def test_row_gate_moved_honors_explicit_false() -> None:
    row = {"gate_moved": False, "passed": True, "tryout": False}
    assert row_gate_moved(row) is False
