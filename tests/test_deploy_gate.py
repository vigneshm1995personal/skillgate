"""Deploy gate: try-outs and key/config errors must not move the pack gate."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.deploy import deploy_allowed, require_passing_check
from skillgate_ai.deploy_gate import (
    infer_gate_moved,
    local_gate,
    newest_gate_moving_row,
    pack_gate_decision,
    row_gate_moved,
    row_is_tryout,
    run_gate_decision,
    run_gate_summary,
)
from skillgate_ai.history import append_eval, load_history


def _append(
    pack: Path,
    *,
    run_id: str,
    passed: bool | None = True,
    tryout: bool = False,
    error: dict | None = None,
    gate_moved: bool | None = None,
) -> None:
    (pack / "evals").mkdir(parents=True, exist_ok=True)
    append_eval(
        pack,
        run_id=run_id,
        passed=passed if passed is not None else False,
        report={"tryout": tryout, "skill": pack.name} if tryout or passed is not None else None,
        error=error,
        tryout=tryout,
        gate_moved=gate_moved,
    )


def test_tryout_and_key_error_do_not_move_gate(tmp_path: Path) -> None:
    """QA G-1: green full run, key-error --case, passing --case try-out."""
    pack = tmp_path / "pdf"
    pack.mkdir()
    _append(pack, run_id="full-green", passed=True, tryout=False)
    _append(
        pack,
        run_id="key-bad",
        passed=None,
        tryout=True,
        error={"message": "The provider did not accept this key.", "hint": None},
        gate_moved=False,
    )
    _append(pack, run_id="tryout-ok", passed=True, tryout=True, gate_moved=False)

    decision, reason = pack_gate_decision(pack)
    assert decision == "cleared"
    assert deploy_allowed(pack) is True
    require_passing_check(pack, name="pdf")  # no raise

    rows = load_history(pack, limit=0)
    key_row = next(r for r in rows if r["run_id"] == "key-bad")
    d, _ = run_gate_decision(key_row)
    assert d == "pending"
    assert key_row.get("gate") != "red"


def test_started_failure_with_error_blocks_deploy(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    pack.mkdir()
    _append(pack, run_id="full-green", passed=True, tryout=False)
    append_eval(
        pack,
        run_id="run-fail",
        passed=False,
        error={"message": "harness died"},
        tryout=False,
        gate_moved=True,
    )
    assert pack_gate_decision(pack)[0] == "blocked"
    assert deploy_allowed(pack) is False


def test_cli_deploy_matches_pack_gate_after_tryout_sequence(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    pack.mkdir()
    _append(pack, run_id="full-green", passed=True)
    _append(
        pack,
        run_id="auth-fail",
        passed=None,
        tryout=False,
        error={"message": "No agent is available to run checks.", "hint": "Add a key"},
        gate_moved=False,
    )
    assert pack_gate_decision(pack)[0] == "cleared"
    assert deploy_allowed(pack) is True


def test_run_gate_summary_running_record() -> None:
    assert run_gate_summary({"status": "running", "tryout": False}) == {
        "kind": "official",
        "moves_gate": True,
        "decision": "pending",
        "reason": "Check is still running.",
        "tryout_reason": None,
    }


def test_run_gate_summary_drops_reason_for_official() -> None:
    assert run_gate_summary({"passed": True}, tryout_reason="subset")["tryout_reason"] is None


def test_run_gate_summary_error_row() -> None:
    out = run_gate_summary({"passed": None, "error": {"message": "x"}})
    assert out["moves_gate"] is False
    assert out["decision"] == "pending"


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
