"""Pack CLI: run history."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.cli.history_format import (
    _print_history_rows,
    _print_history_run,
    _print_skill_versions,
)
from skillgate_ai.errors import SkillGateError


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
