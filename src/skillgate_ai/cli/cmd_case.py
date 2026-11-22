"""CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.errors import SkillGateError


def case_add_cmd(
    pack: Path | None = typer.Argument(None, help="Skill pack"),
    prompt: str = typer.Option(..., "--prompt", help="What the agent should do"),
    case_id: str | None = typer.Option(None, "--id", help="Optional check id"),
    expected: str | None = typer.Option(None, "--expected", help="Expected text in the output"),
    output_path: str | None = typer.Option(None, "--output", help="Output file to compare"),
    inputs: list[Path] | None = typer.Option(
        None, "--input", "--fixture", help="Input/fixture file to copy into this skill"
    ),
    no_trigger: bool = typer.Option(
        False, "--no-trigger", help="This check should not run the skill"
    ),
    force: bool = typer.Option(False, "--force", help="Replace a check that already uses this id"),
    output_optional: bool = typer.Option(
        False,
        "--output-optional",
        help="Accept a missing or empty output file. Expected stays reference text.",
    ),
) -> None:
    """Add a check to this skill's Dataset."""
    from skillgate_ai.pack_edit import add_pack_case

    try:
        dest = base._resolve_pack_arg(pack)
        pack_out, warning = add_pack_case(
            dest,
            prompt=prompt,
            case_id=case_id,
            expected=expected,
            output_path=output_path,
            should_trigger=not no_trigger,
            inputs=[str(path) for path in inputs] if inputs else None,
            force=force,
            output_optional=output_optional,
        )
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    except ValueError as exc:
        base.console.print(str(exc))
        raise typer.Exit(1) from None
    from skillgate_ai.pack_schema import case_id_slug

    added = (
        case_id_slug(case_id)
        if str(case_id or "").strip()
        else (pack_out.cases[-1].id if pack_out.cases else prompt)
    )
    base.console.print(f"Added check {added}.")
    if warning:
        base.console.print(warning)
