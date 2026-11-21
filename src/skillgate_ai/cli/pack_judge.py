"""Pack CLI: judge pack commands."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.errors import SkillGateError


def register_judge_remove_question(judge_app: typer.Typer) -> None:
    from skillgate_ai import cli as _cli

    def judge_remove_question(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        question_id: str = typer.Option(..., "--id", help="Extra question id"),
    ) -> None:
        """Remove an extra scoring question. Skill Gate’s six stay."""
        from skillgate_ai.pack_edit import remove_judge_question

        try:
            dest = _cli._resolve_pack_arg(pack)
            remove_judge_question(dest, question_id)
        except SkillGateError as exc:
            _cli.console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        _cli.console.print(f"Removed {question_id}.")

    judge_app.command("remove-question")(judge_remove_question)


def register_judge_set_question(judge_app: typer.Typer) -> None:
    from skillgate_ai import cli as _cli

    def judge_set_question(
        pack: Path | None = typer.Argument(None, help="Skill pack"),
        question_id: str = typer.Option(..., "--id"),
        on_fail: str = typer.Option(..., "--on-fail", help="Fail the check | Warn only"),
    ) -> None:
        """Change Fail vs warn for a built-in or extra question."""
        from skillgate_ai.pack_edit import set_question_on_fail

        try:
            dest = _cli._resolve_pack_arg(pack)
            set_question_on_fail(dest, question_id, on_fail)
        except SkillGateError as exc:
            _cli.console.print(exc.render())
            raise typer.Exit(exc.exit_code) from None
        _cli.console.print(f"Updated {question_id}.")

    judge_app.command("set-question")(judge_set_question)
