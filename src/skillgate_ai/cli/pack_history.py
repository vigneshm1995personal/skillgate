"""Pack CLI: run history."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.errors import SkillGateError


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
            who = report.get("scored_by") if isinstance(report.get("scored_by"), str) else ""
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


def register_history_app(app: typer.Typer) -> typer.Typer:
    history_app = typer.Typer(
        add_completion=False,
        invoke_without_command=True,
        help="Show recent check runs for this skill.",
    )
    app.add_typer(history_app, name="history")
    return history_app


def register_history_callback(history_app: typer.Typer) -> None:
    from skillgate_ai import cli as _cli

    def history_cmd(
        ctx: typer.Context,
        pack: Path | None = typer.Option(None, "--pack", help="Skill pack"),
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        """Show recent check runs for this skill."""
        if ctx.invoked_subcommand:
            return
        from skillgate_ai.history import load_history

        try:
            dest = _cli._resolve_pack_arg(pack)
            rows = load_history(dest, limit=20)
        except SkillGateError as exc:
            _cli.console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        if json_out:
            from skillgate_ai.cli import _emit_json

            _emit_json(rows)
            return
        _print_history_rows(rows)
        _print_skill_versions(dest)

    history_app.callback(invoke_without_command=True)(history_cmd)


def _find_history_row(run_id: str, pack: Path | None) -> tuple[dict, Path | None]:
    from skillgate_ai import cli as _cli
    from skillgate_ai.catalog import catalog_entries
    from skillgate_ai.history import load_history

    row = None
    skill_path = None
    if pack is not None:
        dest = _cli._resolve_pack_arg(pack)
        skill_path = dest
        for item in load_history(dest, limit=0):
            if str(item.get("run_id") or "") == run_id:
                row = item
                break
    else:
        for entry in catalog_entries(_cli._boot()):
            path = Path(entry["absolute"])
            for item in load_history(path, limit=0):
                if str(item.get("run_id") or "") == run_id:
                    row = item
                    skill_path = path
                    break
            if row is not None:
                break
        if row is None:
            dest = _cli._resolve_pack_arg(None)
            skill_path = dest
            for item in load_history(dest, limit=0):
                if str(item.get("run_id") or "") == run_id:
                    row = item
                    break
    if row is None:
        raise SkillGateError(f"No run named {run_id}.")
    return row, skill_path


def _print_history_run(row: dict) -> None:
    from skillgate_ai import cli as _cli

    report = row.get("report") if isinstance(row.get("report"), dict) else {}
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
    tasks = report.get("tasks") if isinstance(report.get("tasks"), list) else []
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


def register_history_show(history_app: typer.Typer) -> None:
    from skillgate_ai import cli as _cli

    def history_show(
        run_id: str = typer.Argument(..., help="Run id"),
        pack: Path | None = typer.Option(None, "--pack", help="Skill pack"),
        json_out: bool = typer.Option(False, "--json"),
    ) -> None:
        """Show one saved run."""
        try:
            row, skill_path = _find_history_row(run_id, pack)
        except SkillGateError as exc:
            _cli.console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        if json_out:
            from skillgate_ai.api_payloads import history_row_to_run
            from skillgate_ai.cli import _emit_json

            _emit_json(history_row_to_run(row, skill_path or Path(".")))
            return
        _print_history_run(row)

    history_app.command("show")(history_show)
