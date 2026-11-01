"""Re-score a saved run from outputs and spans. Does not call the agent or judge."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from skillgate_ai.errors import SkillGateError
from skillgate_ai.history import load_history
from skillgate_ai.score import finish_task, score_run, spec_for_task


def find_history_run(pack: Path, run_id: str) -> dict[str, Any] | None:
    wanted = str(run_id or "").strip()
    if not wanted:
        return None
    for item in load_history(pack, limit=0):
        if str(item.get("run_id") or "") == wanted:
            return item
    return None


def lookup_history_run(run_id: str, dest: Path) -> dict[str, Any]:
    row = find_history_run(dest, run_id)
    if row is None:
        raise SkillGateError(f"No run named {run_id}.", exit_code=2)
    return row


def rescore_saved_run(pack: Path, row: dict[str, Any]) -> dict[str, Any]:
    """Recompute log/text extras with the same scorer live check uses."""
    from skillgate_ai.report import hydrate_report_spans

    out = deepcopy(row)
    report = out.get("report") if isinstance(out.get("report"), dict) else {}
    report = hydrate_report_spans(dict(report))
    skill_text = _skill_text(pack)
    tasks = [item for item in (report.get("tasks") or []) if isinstance(item, dict)]
    passed_count = 0
    failed_ids: list[str] = []
    for task in tasks:
        spec = spec_for_task(pack, task)
        judge = dict(task.get("judge") or {}) if isinstance(task.get("judge"), dict) else {}
        outputs = task.get("outputs") if isinstance(task.get("outputs"), list) else []
        spans = task.get("spans") if isinstance(task.get("spans"), list) else []
        scores = task.get("scores") if isinstance(task.get("scores"), list) else []
        stamped = score_run(
            spec=spec,
            judged=judge,
            outputs=outputs,
            spans=spans,
            scores=scores,
            skill_text=skill_text,
            expect_skill=task.get("expect_skill"),
        )
        gate = stamped.get("passed")
        task["judge"] = stamped
        task["passed"] = gate
        task["failures"] = list(stamped.get("reasons") or [])
        finish_task(task, gate)
        if gate is True:
            passed_count += 1
        elif gate is False:
            failed_ids.append(str(task.get("id") or task.get("task_id") or ""))
    report["tasks"] = tasks
    report["passed_count"] = passed_count
    report["task_count"] = len(tasks)
    report["failed_task_ids"] = [item for item in failed_ids if item]
    if any(task.get("passed") is False for task in tasks):
        report["passed"] = False
        report["gate"] = "red"
        out["passed"] = False
        out["gate"] = "red"
    elif tasks and all(task.get("passed") is True for task in tasks):
        review = any(
            task.get("review") or (isinstance(task.get("judge"), dict) and task["judge"].get("review"))
            for task in tasks
        )
        warning = any(str(task.get("status") or "") == "warning" for task in tasks)
        report["passed"] = True
        if review:
            report["gate"] = "needs review"
        elif warning:
            report["gate"] = "warning"
        else:
            report["gate"] = "green"
        out["passed"] = True
        out["gate"] = report["gate"]
    out.pop("status", None)
    out["report"] = report
    return out


def _skill_text(pack: Path) -> str | None:
    skill = pack / "SKILL.md"
    if not skill.is_file():
        return None
    text = skill.read_text(encoding="utf-8")
    return text if text.strip() else None
