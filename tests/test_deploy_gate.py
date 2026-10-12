"""Deploy gate: try-outs and key/config errors must not move the pack gate."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.deploy import deploy_allowed, require_passing_check
from skillgate_ai.deploy_gate import pack_gate_decision, run_gate_decision
from skillgate_ai.history import append_eval, load_history

# append_eval used directly in failure-block test


def _append(
    pack: Path,
    *,
    run_id: str,
    passed: bool | None = True,
    tryout: bool = False,
    error: dict | None = None,
    gate_moved: bool | None = None,
) -> None:
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
        error={"message": "No model key found.", "hint": "Add a key"},
        gate_moved=False,
    )
    assert pack_gate_decision(pack)[0] == "cleared"
    assert deploy_allowed(pack) is True
