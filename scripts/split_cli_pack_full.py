#!/usr/bin/env python3
"""Split cli_pack.py into cli/pack_*.py per docs/specs/split-giant-files.md."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src/skillgate_ai/cli"

PACK_CASE = '''"""Pack CLI: case list/edit/import/bind."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.cli.pack_case import _output_optional_flag
from skillgate_ai.errors import SkillGateError


def _output_optional_flag(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "y"}


def register_case_list(case_app: typer.Typer) -> None:
    def case_list(pack: Path | None = typer.Argument(None, help="Skill pack")) -> None:
        """List saved checks."""
        from skillgate_ai.case_pack import load_case_pack
        from skillgate_ai.cli import _resolve_pack_arg, console

        try:
            dest = _resolve_pack_arg(pack)
            loaded = load_case_pack(dest)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        if loaded is None or not loaded.cases:
            console.print("No checks saved.")
            return
        for case in loaded.cases:
            console.print(f"{case.id}  {case.status}  {case.prompt}")

    case_app.command("list")(case_list)


def register_case_remove(case_app: typer.Typer) -> None:
    def case_remove(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        case_id: str = typer.Option(..., "--id", help="Check id to remove"),
    ) -> None:
        """Remove a custom check. Original seed checks stay."""
        from skillgate_ai.pack_edit import remove_pack_case
        from skillgate_ai.cli import _resolve_pack_arg, console

        try:
            dest = _resolve_pack_arg(pack)
            remove_pack_case(dest, case_id)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        console.print(f"Removed {case_id}.")

    case_app.command("remove")(case_remove)


def register_case_edit(case_app: typer.Typer) -> None:
    def case_edit(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        case_id: str = typer.Option(..., "--id", help="Check id"),
        prompt: str | None = typer.Option(None, "--prompt"),
        expected: str | None = typer.Option(None, "--expected"),
        output_path: str | None = typer.Option(None, "--output"),
        output_optional: str | None = typer.Option(
            None,
            "--output-optional",
            help="true accepts a missing or empty output file and keeps Expected as reference text",
        ),
    ) -> None:
        """Edit a saved check."""
        from skillgate_ai.pack_edit import edit_pack_case
        from skillgate_ai.cli import _resolve_pack_arg, console

        optional_flag = _output_optional_flag(output_optional)
        try:
            dest = _resolve_pack_arg(pack)
            edit_pack_case(
                dest,
                case_id,
                prompt=prompt,
                expected=expected,
                output_path=output_path,
                output_optional=optional_flag,
            )
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        console.print(f"Updated {case_id}.")

    case_app.command("edit")(case_edit)


def register_case_import(case_app: typer.Typer) -> None:
    def case_import_cmd(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        file: Path = typer.Argument(..., help="CSV, JSONL, or YAML file"),
        dry_run: bool = typer.Option(False, "--dry-run", help="Preview without writing"),
        on_conflict: str = typer.Option(
            "fail",
            "--on-conflict",
            help="When a check id already exists: fail, skip, or replace",
        ),
    ) -> None:
        """Import checks from a dataset file into evals/cases.yaml."""
        from skillgate_ai.case_import import CaseImportError, apply_case_import
        from skillgate_ai.cli import _resolve_pack_arg, console

        conflict = on_conflict.strip().lower()
        if conflict not in {"fail", "skip", "replace"}:
            console.print("--on-conflict must be fail, skip, or replace.")
            raise typer.Exit(2)
        try:
            dest = _resolve_pack_arg(pack)
            data = file.expanduser().read_bytes()
            plan = apply_case_import(
                dest,
                data,
                filename=file.name,
                on_conflict=conflict,  # type: ignore[arg-type]
                dry_run=dry_run,
            )
        except CaseImportError as exc:
            console.print(exc.message)
            for row in exc.rows:
                console.print(f"  row {row.row}: {row.error}")
            raise typer.Exit(exc.exit_code) from None
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        for row in plan.rows:
            if row.error:
                console.print(f"row {row.row}  error  {row.error}")
                continue
            action = row.action if dry_run else "imported"
            prompt = row.prompt if len(row.prompt) <= 48 else row.prompt[:45] + "..."
            console.print(f"row {row.row}  {row.id:<24}  {action:<8}  {prompt}")
        for warn in plan.warnings:
            console.print(warn)
        if dry_run:
            console.print(f"Would import {len(plan.checks)} check(s) from {plan.format}.")
        else:
            console.print(f"Imported {len(plan.checks)} check(s) from {plan.format}.")

    case_app.command("import")(case_import_cmd)


def register_case_bind(case_app: typer.Typer) -> None:
    def case_bind(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        inherit: bool = typer.Option(True, "--inherit/--no-inherit"),
        expand: bool = typer.Option(False, "--expand"),
    ) -> None:
        """Attach this skill’s sample files to checks that need them."""
        from skillgate_ai.pack_edit import bind_case_files
        from skillgate_ai.cli import _resolve_pack_arg, console

        try:
            dest = _resolve_pack_arg(pack)
            bind_case_files(dest, inherit=inherit, expand=expand)
        except SkillGateError as exc:
            console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        console.print("Bound sample files to checks.")

    case_app.command("bind")(case_bind)
'''

# Fix erroneous self-import in PACK_CASE template
PACK_CASE = PACK_CASE.replace(
    "from skillgate_ai.cli.pack_case import _output_optional_flag\n", ""
)