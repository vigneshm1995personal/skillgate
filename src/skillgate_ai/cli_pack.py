"""CLI commands that match OSS UI writes: import, skill files, cases, history."""

from __future__ import annotations

import typer


def _output_optional_flag(value: str | None) -> bool | None:
    from skillgate_ai.cli.pack_case import _output_optional_flag as _impl

    return _impl(value)


def register_pack_commands(
    app: typer.Typer,
    case_app: typer.Typer,
    judge_app: typer.Typer,
) -> None:
    from skillgate_ai.cli.pack_commands import register_pack_commands as _impl

    _impl(app, case_app, judge_app)
