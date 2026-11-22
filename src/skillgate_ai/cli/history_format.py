"""History CLI formatting helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _print_history_rows(rows: list) -> None:
    from skillgate_ai import cli as _cli
    from skillgate_ai.judge_copy import customer_scorer_name, scored_by_phrase

    if not rows:
        _cli.console.print("No runs yet.")
        return
    for row in reversed(rows):
        report = row.get("report") if isinstance(row.get("report"), dict) else {}
        passed = row.get("passed")
        if passed is None:
            err = row.get("error") if isinstance(row.get("error"), dict) else {}
            message = str((err or {}).get("message") or "")
            if "cannot run" in message.lower():
                gate = "cannot-run"
            elif report.get("tasks") or str(report.get("gate") or "") == "not scored":
                gate = "not scored"
            else:
                gate = "not run"
            who = "Not scored"
        else:
            scored_by = report.get("scored_by")
            who = scored_by if isinstance(scored_by, str) else ""
            if not who or "openai decisions" in who.lower() or "vercel ai gateway" in who.lower():
                stamp = None
                if isinstance(report.get("config"), dict):
                    stamp = report["config"].get("judge")
                who = scored_by_phrase(
                    customer_scorer_name(stamp if isinstance(stamp, dict) else None)
                )
            row_gate = str(report.get("gate") or row.get("gate") or "")
            if passed is True and row_gate == "needs review":
                gate = "review"
            else:
                gate = ("pass" if passed else "fail").ljust(4)
        passed = report.get("passed_count")
        total = report.get("task_count")
        if passed is not None and total is not None:
            counts = f" {passed}/{total}".rjust(6)
        elif row.get("error"):
            counts = "   —/—"
        else:
            counts = "      "
        ts = str(row.get("ts") or "")
        date = ts[:10] if ts else ""
        date_bit = f"  {date}" if date else ""
        _cli.console.print(f"{row.get('run_id')}  {gate}{counts}{date_bit}  {who}")


def _print_skill_versions(pack: Path) -> None:
    from skillgate_ai import cli as _cli
    from skillgate_ai.compare_git import list_skill_git_versions

    versions = list_skill_git_versions(pack)
    _cli.console.print("Versions")
    if not versions:
        _cli.console.print("No versions recorded yet.")
        return
    for item in versions:
        when = str(item.get("created_at") or "")[:10]
        date_bit = f"  {when}" if when else ""
        _cli.console.print(f"{item['ref']}{date_bit}")


def _print_history_run(row: dict) -> None:
    from skillgate_ai import cli as _cli

    raw_report = row.get("report")
    report: dict[str, Any] = raw_report if isinstance(raw_report, dict) else {}
    passed_flag = row.get("passed")
    err = row.get("error") if isinstance(row.get("error"), dict) else {}
    cannot_run = "cannot run" in str((err or {}).get("message") or "").lower()
    if passed_flag is True and str(report.get("gate") or "") == "needs review":
        gate = "review"
    elif passed_flag is True:
        gate = "pass"
    elif passed_flag is False:
        gate = "fail"
    elif cannot_run:
        gate = "cannot-run"
    elif report.get("tasks") or str(report.get("gate") or "") == "not scored":
        gate = "not scored"
    else:
        gate = "not run"
    passed = report.get("passed_count")
    total = report.get("task_count")
    counts = f"  {passed}/{total}" if passed is not None and total is not None else ""
    _cli.console.print(f"{row.get('run_id')}  {gate}{counts}")
    err = row.get("error")
    if isinstance(err, dict):
        message = str(err.get("message") or "").strip()
        hint = str(err.get("hint") or "").strip()
        if message:
            _cli.console.print(f"  {message}")
        if hint:
            _cli.console.print(f"  {hint}")
    raw_tasks = report.get("tasks")
    tasks: list[Any] = raw_tasks if isinstance(raw_tasks, list) else []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        tid = str(task.get("id") or task.get("task_id") or "")
        ok = task.get("passed")
        if ok is True and (task.get("review") or task.get("status") == "unsure"):
            mark = "review"
        elif ok is True:
            mark = "pass"
        elif ok is False:
            mark = "fail"
        else:
            mark = "not scored"
        reason = ""
        if mark == "review":
            reason = "  unsure, needs review"
        elif ok is False:
            happened = str(task.get("happened") or "").strip()
            if happened:
                reason = f"  {happened}"
            else:
                failures = task.get("failures")
                if isinstance(failures, list) and failures:
                    reason = f"  {failures[0]}"
        _cli.console.print(f"  {tid}  {mark}{reason}")
