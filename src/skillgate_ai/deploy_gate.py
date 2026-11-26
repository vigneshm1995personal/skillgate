"""Pack deploy gate: one rule for CLI, API, and UI."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from skillgate_ai.history import load_history


def row_is_tryout(row: Mapping[str, Any], report: Mapping[str, Any] | None = None) -> bool:
    rep = (
        report
        if report is not None
        else (row.get("report") if isinstance(row.get("report"), dict) else None)
    )
    return bool(row.get("tryout") or (rep or {}).get("tryout"))


def infer_gate_moved(
    *,
    tryout: bool,
    error: Mapping[str, Any] | None,
    passed: bool | None,
    explicit: bool | None = None,
) -> bool:
    if explicit is not None:
        return bool(explicit)
    if tryout:
        return False
    if error is not None and passed is None:  # noqa: SIM103
        return False
    return True


def row_gate_moved(row: Mapping[str, Any]) -> bool:
    """Whether this history row may advance or block Deploy for the pack."""
    report = row.get("report") if isinstance(row.get("report"), dict) else None
    error = row.get("error") if isinstance(row.get("error"), dict) else None
    explicit = row.get("gate_moved")
    if isinstance(explicit, bool):
        return explicit
    return infer_gate_moved(
        tryout=row_is_tryout(row, report),
        error=error,
        passed=row.get("passed") if row.get("passed") is not None else None,
        explicit=None,
    )


RUNNING_GATE_REASON = "Check is still running."


def run_gate_summary(row: Mapping[str, Any], *, tryout_reason: str | None = None) -> dict[str, Any]:
    """Uniform gate block for a history row or a live run record."""
    report = row.get("report") if isinstance(row.get("report"), dict) else None
    tryout = row_is_tryout(row, report)
    if row.get("status") == "running":
        decision, reason = "pending", RUNNING_GATE_REASON
    elif isinstance(row.get("gate_decision"), str) and row.get("gate_reason"):
        decision, reason = str(row["gate_decision"]), str(row["gate_reason"])
    else:
        decision, reason = run_gate_decision(row)
    return {
        "kind": "tryout" if tryout else "official",
        "moves_gate": row_gate_moved(row),
        "decision": decision,
        "reason": reason,
        "tryout_reason": tryout_reason if tryout else None,
    }


def run_gate_decision(row: Mapping[str, Any]) -> tuple[str, str]:
    """Per-run gate_decision for history/UI (not always the pack-level gate)."""
    report = row.get("report") if isinstance(row.get("report"), dict) else None
    error = row.get("error") if isinstance(row.get("error"), dict) else None
    tryout = row_is_tryout(row, report)
    status = "error" if error else "done"
    if not row_gate_moved(row):
        if tryout:
            return "pending", "Single-check runs do not unlock Deploy."
        if status == "error":
            return "pending", "This run ended in error and did not change the gate."
        return "pending", "This run did not change the gate."
    if status == "error" or row.get("passed") is False:
        return "blocked", "Get a passing run to unlock Deploy."
    report_gate = str((report or {}).get("gate") or row.get("gate") or "")
    if report_gate == "needs review":
        return "pending", "The judge was unsure. Review the run."
    if row.get("passed"):
        return "cleared", "Checks passed — Deploy is unlocked."
    return "pending", "Run checks to set the gate."


def newest_gate_moving_row(rows: Sequence[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    for row in reversed(rows):
        if row_gate_moved(row):
            return row
    return None


def _workspace_trusted_for_gate(pack: Path | str) -> bool:
    """Gate / deploy UI uses workspace-trusted packs only (not ``--allow-root`` mounts)."""
    from skillgate_ai.fs_anchor import FsAnchor
    from skillgate_ai.paths import PathTraversalError
    from skillgate_ai.trusted_roots import pack_access_root

    try:
        anchor, _ = pack_access_root(pack)
    except PathTraversalError:
        return False
    return anchor is not FsAnchor.ALLOW_ROOT


def pack_gate_decision(pack: Path | str) -> tuple[str, str]:
    """Pack-level deploy gate (newest gate-moving run)."""
    if not _workspace_trusted_for_gate(pack):
        return "pending", "Run checks to set the gate."
    rows = load_history(pack, limit=0)
    row = newest_gate_moving_row(rows)
    if row is None:
        return "pending", "Run checks to set the gate."
    return run_gate_decision(row)


def deploy_allowed(pack: Path | str) -> bool:
    return pack_gate_decision(pack)[0] == "cleared"


def local_gate(
    passed: bool | None,
    *,
    status: str,
    tryout: bool,
    gate_moved: bool | None = None,
    report: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    """Live run completion (API worker). Mirrors run_gate_decision on a synthetic row."""
    moved = infer_gate_moved(
        tryout=tryout,
        error={"message": "error"} if status == "error" else None,
        passed=passed,
        explicit=gate_moved,
    )
    row: dict[str, Any] = {
        "passed": passed,
        "tryout": tryout,
        "gate_moved": moved,
    }
    if report:
        row["report"] = report
    if status == "error":
        row["error"] = {"message": "error"}
        row["passed"] = None
    return run_gate_decision(row)
