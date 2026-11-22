"""CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.errors import SkillGateError


def checks_show_cmd(
    check_id: str = typer.Argument(..., help="Built-in or custom check id"),
    pack: Path | None = typer.Option(None, "--pack", help="Skill pack for a custom check"),
) -> None:
    """Print the judge prompt for this check."""
    from skillgate_ai.checks_show import prompt_for_id

    try:
        dest = base._resolve_pack_arg(pack) if pack is not None else None
        row = prompt_for_id(check_id, pack=dest)
    except SkillGateError as exc:
        base.console.print(exc.render(), markup=False)
        raise typer.Exit(exc.exit_code) from None
    sys.stdout.write(row["prompt"])
    if not str(row["prompt"]).endswith("\n"):
        sys.stdout.write("\n")


def judge_show(
    pack: Path | None = typer.Argument(
        None, help="Skill pack (default: this folder or skills/pdf)"
    ),
    case_id: str | None = typer.Option(None, "--case", help="Case id"),
    json_out: bool = typer.Option(False, "--json", help="Resolved spec JSON"),
) -> None:
    """Print built-in questions, then extras."""
    from skillgate_ai.case_pack import load_case_pack, pack_judge_dict
    from skillgate_ai.judge_spec import resolve_judge_spec
    from skillgate_ai.project_config import load_project_judge

    try:
        dest = base._resolve_pack_arg(pack)
        loaded = load_case_pack(dest)
        case_block = None
        if case_id:
            from skillgate_ai.pack_schema import case_id_slug

            wanted = case_id_slug(case_id)
            found = False
            if loaded is not None:
                for case in loaded.cases:
                    if case.id == wanted:
                        found = True
                        if case.judge is not None:
                            case_block = case.judge.to_sparse_dict()
                        break
            if not found:
                raise SkillGateError(f"No check named {case_id}.")
        spec = resolve_judge_spec(
            project=load_project_judge(base._boot()),
            pack=pack_judge_dict(loaded),
            case=case_block,
        )
        from skillgate_ai.wording_facts import (
            attach_wording_questions,
            compile_wording_rules,
            wording_ask,
        )

        skill_text = (
            (dest / "SKILL.md").read_text(encoding="utf-8")
            if (dest / "SKILL.md").is_file()
            else None
        )
        spec = attach_wording_questions(spec, skill_text)
        wording_rules = compile_wording_rules(skill_text)
        wording_label = wording_ask(wording_rules) if wording_rules else None
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    if json_out:
        payload = {
            "questions": [
                {
                    "id": q.id,
                    "type": q.type,
                    "ask": q.ask,
                    "on_fail": q.on_fail,
                    "builtin": q.builtin,
                }
                for q in spec.questions
            ]
        }
        if wording_label:
            payload["text_checks"] = [{"id": "wording", "ask": wording_label, "source": "text"}]
        base._emit_json(payload)
        return
    base.console.print("Skill Gate questions (always asked)")
    for question in spec.builtins:
        severity = "Warn only" if question.on_fail == "warn" else "Fail the check"
        base.console.print(f"  {question.label}  {severity}")
    extras = spec.extras
    if extras:
        base.console.print("Your questions")
        for question in extras:
            kind = {"predicate": "Yes/No", "choice": "Pick one", "score": "Score"}[question.type]
            severity = "Warn only" if question.on_fail == "warn" else "Fail the check"
            base.console.print(f"  {question.label}  {kind}  {severity}")
    else:
        base.console.print("No extra questions.")
    if wording_label:
        base.console.print("Text checks from the skill")
        base.console.print(f"  {wording_label}  Yes/No  Fail the check")


def judge_reset(
    pack: Path | None = typer.Argument(None, help="Skill pack"),
) -> None:
    """Drop extras and Fail vs warn overrides. Built-ins stay."""
    from skillgate_ai.case_pack import reset_pack_judge

    try:
        dest = base._resolve_pack_arg(pack)
        reset_pack_judge(dest)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    base.console.print("Extra scoring questions removed. Skill Gate’s six stay.")


def judge_add_question_cmd(
    pack: Path | None = typer.Argument(None, help="Skill pack"),
    ask: str = typer.Option(..., "--ask", help="Question text"),
    kind: str = typer.Option("Yes/No", "--type", help="Yes/No | pick one | score"),
    question_id: str | None = typer.Option(None, "--id", help="Optional question id"),
    warn_only: bool = typer.Option(False, "--warn-only", help="Warn instead of failing the check"),
    choices: list[str] | None = typer.Option(
        None, "--choices", help="Pick-one options (repeatable)"
    ),
) -> None:
    """Add an extra scoring question to this skill."""
    from skillgate_ai.pack_edit import add_judge_question

    try:
        dest = base._resolve_pack_arg(pack, default_pdf=False)
        add_judge_question(
            dest,
            ask=ask,
            kind=kind,
            question_id=question_id,
            on_fail="warn" if warn_only else "block",
            choices=choices,
        )
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    base.console.print(ask)
