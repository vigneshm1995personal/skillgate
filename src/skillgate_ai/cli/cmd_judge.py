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


def judge_provider_show() -> None:
    """Who scores live checks."""
    from skillgate_ai.judge_providers.decision import NEEDS_DECISION_MODEL_HINT
    from skillgate_ai.judge_settings import load_judge_settings
    from skillgate_ai.judge_setup import format_provider_selection

    root = base._boot()
    settings = load_judge_settings(root)
    base.console.print(format_provider_selection(settings))
    provider = str(getattr(settings, "provider", "") or "auto").strip().lower() or "auto"
    if provider in {"", "auto", "skip"}:
        base.console.print(NEEDS_DECISION_MODEL_HINT)
        raise typer.Exit(2)


def judge_provider_set(
    provider: str = typer.Argument(
        ..., help="A decision-model endpoint id, or auto to clear the selection"
    ),
    base_url: str | None = typer.Option(None, "--base-url"),
    region: str | None = typer.Option(None, "--region"),
    model: str | None = typer.Option(None, "--model"),
    account_id: str | None = typer.Option(
        None, "--account-id", help="Account id for this decision model"
    ),
    decisions_path: str | None = typer.Option(None, "--decisions-path", hidden=True),
    key_env: list[str] | None = typer.Option(None, "--key-env", help=base._KEY_ENV_HELP),
) -> None:
    """Write `.skillgate/judge`. Stores env var names, never key values."""
    from skillgate_ai.judge_settings import save_judge_settings

    root = base._boot()
    try:
        settings = save_judge_settings(
            root,
            provider=provider,
            region=region,
            model=model,
            base_url=base_url,
            decisions_path=decisions_path,
            key_env=key_env,
            account_id=account_id,
        )
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    from skillgate_ai.judge_setup import format_provider_selection

    base.console.print(format_provider_selection(settings))


def _run_judge_test(key_env: list[str] | None, *, verbose: bool = False) -> None:
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.judge import ping_judge

    root = base._boot()
    base._bind_key_env(key_env)
    try:
        result = ping_judge(get_llm_config(root), verbose=verbose)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    base.console.print(str(result.get("message") or ""), soft_wrap=True)
    raise typer.Exit(0 if result.get("ok") else 1)


def judge_test(
    key_env: list[str] | None = typer.Option(None, "--key-env", help=base._KEY_ENV_HELP),
    verbose: bool = typer.Option(False, "--verbose", help=base._VERBOSE_HELP),
) -> None:
    """Test the scoring connection. Never prints the key."""
    _run_judge_test(key_env, verbose=verbose)


def judge_provider_test(
    key_env: list[str] | None = typer.Option(None, "--key-env", help=base._KEY_ENV_HELP),
    verbose: bool = typer.Option(False, "--verbose", help=base._VERBOSE_HELP),
) -> None:
    """Test the scoring connection. Never prints the key."""
    _run_judge_test(key_env, verbose=verbose)
