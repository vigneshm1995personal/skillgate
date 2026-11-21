"""CLI commands."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NoReturn

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.api_payloads import scrub_browser_payload
from skillgate_ai.errors import SkillGateError, timeout_harness_error
from skillgate_ai.gate import run_check
from skillgate_ai.paths import project_root, resolve_user_path
from skillgate_ai.report import format_cli, format_github, report_to_dict


def _present_check(result, *, verbose: bool = False) -> None:
    if result.error:
        base.console.print(result.error["message"], markup=False)
        hint = result.error.get("hint")
        if hint:
            base.console.print(hint, markup=False)
    elif result.report is not None:
        base.console.print(format_cli(result.report))
        if verbose:
            for line in _verbose_scoring_lines(result.report):
                base.console.print(line)


def _verbose_scoring_lines(report) -> list[str]:
    lines: list[str] = []
    for task in report.tasks:
        judge = task.judge if isinstance(task.judge, dict) else {}
        extra = str(judge.get("upstream") or "").strip() if isinstance(judge, dict) else ""
        if extra:
            lines.append(f"  {task.task_id}: {extra}")
    return lines


def _exit_with_error(exc: SkillGateError, *, machine: bool) -> NoReturn:
    if machine:
        base._emit_json(
            {
                "error": exc.message,
                "hint": exc.hint,
                "exit_code": exc.exit_code,
            }
        )
    else:
        base.console.print(exc.render())
    raise typer.Exit(exc.exit_code) from None


def _tryout_checks(target: Path, case_id: str, *, machine: bool) -> list:
    from skillgate_ai.pack_edit import tryout_checks
    from skillgate_ai.paths import is_skill_pack

    dest = resolve_user_path(target, project_root())
    if not is_skill_pack(dest):
        _exit_with_error(
            SkillGateError(
                f"Not a skill pack: {dest}",
                hint="Pass a skill folder with SKILL.md and evals/.",
                exit_code=2,
            ),
            machine=machine,
        )
    try:
        return tryout_checks(dest, case_id)
    except SkillGateError as exc:
        _exit_with_error(exc, machine=machine)
    raise AssertionError("unreachable")


def _finish_gate(result, *, machine: bool, summary: str, verbose: bool) -> NoReturn:
    if not machine and summary != "github":
        _present_check(result, verbose=verbose)
        if result.error or result.report is None:
            raise typer.Exit(result.exit_code)
        if result.expect_fail_notice:
            base.console.print(result.expect_fail_notice)
        raise typer.Exit(result.exit_code)
    if result.error:
        if machine:
            base._emit_json(
                {
                    "error": result.error["message"],
                    "hint": result.error.get("hint"),
                    "exit_code": result.exit_code,
                }
            )
        else:
            base.console.print(result.error["message"], markup=False)
            hint = result.error.get("hint")
            if hint:
                base.console.print(hint, markup=False)
        raise typer.Exit(result.exit_code)
    report = result.report
    if report is None:
        raise typer.Exit(result.exit_code)
    if machine:
        base._emit_json(scrub_browser_payload(report_to_dict(report)))
    else:
        text = format_github(report)
        base.console.print(text)
        gh = os.environ.get("GITHUB_STEP_SUMMARY")
        if gh:
            path = Path(gh)
            prev = path.read_text(encoding="utf-8") if path.exists() else ""
            path.write_text(prev + text, encoding="utf-8")
    if result.expect_fail_notice:
        if machine:
            sys.stderr.write(f"{result.expect_fail_notice}\n")
        else:
            base.console.print(result.expect_fail_notice)
    raise typer.Exit(result.exit_code)


def _run_gate(
    *,
    target: Path,
    skill: Path | None,
    harness: str | None,
    sandbox: str,
    expect_fail: bool,
    summary: str,
    json_out: bool,
    model: str | None,
    timeout: int | None,
    temperature: float | None,
    reasoning_effort: str | None,
    key_env: list[str] | None = None,
    case_id: str | None = None,
    no_judge: bool = False,
    verbose: bool = False,
) -> None:
    base._bind_key_env(key_env)
    machine = json_out or summary == "json"
    checks = None
    tryout = False
    if case_id:
        checks = _tryout_checks(target, case_id, machine=machine)
        tryout = True
    try:
        result = run_check(
            target,
            skill=skill,
            harness=harness,
            sandbox=sandbox,
            expect_fail=expect_fail,
            model=model,
            timeout=timeout,
            temperature=temperature,
            reasoning_effort=reasoning_effort,
            source="cli",
            checks=checks,
            tryout=tryout,
            no_judge=no_judge,
        )
    except Exception as exc:  # noqa: BLE001 — TimeoutExpired must not dump the prompt
        blocked = timeout_harness_error(exc)
        if blocked is None:
            raise
        _exit_with_error(blocked, machine=machine)
    _finish_gate(result, machine=machine, summary=summary, verbose=verbose)


def check_pack(
    pack: Path = typer.Argument(..., help="Skill pack directory (SKILL.md + evals/)"),
    harness: str | None = typer.Option(None, "--harness", help=base._HARNESS_HELP),
    sandbox: str = typer.Option("local", "--sandbox", help=base._SANDBOX_HELP),
    expect_fail: bool = typer.Option(
        False,
        "--expect-fail",
        help="Exit 0 only if the suite is red (sabotaged / intentional-fail)",
    ),
    summary: str = typer.Option("cli", "--summary", help="cli | github | json"),
    json_out: bool = typer.Option(False, "--json", help="Machine JSON (not the primary UX)"),
    model: str | None = typer.Option(None, "--model", help="Requested model id"),
    timeout: int | None = typer.Option(None, "--timeout", help="Per-task timeout seconds"),
    temperature: float | None = typer.Option(None, "--temperature", help="Temperature (0–2)"),
    reasoning_effort: str | None = typer.Option(
        None, "--reasoning-effort", help="Reasoning effort: low | medium | high | ultra"
    ),
    key_env: list[str] | None = typer.Option(None, "--key-env", help=base._KEY_ENV_HELP),
    case_id: str | None = typer.Option(
        None, "--case", "--id", help="Run this check only (try-out)"
    ),
    no_judge: bool = typer.Option(
        False,
        "--no-judge",
        help="Skip the decision model (quality is not scored). Still needs a signed-in agent.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Print the sanitized upstream scoring reason when scoring cannot run.",
    ),
) -> None:
    """Exit 0 if green, 1 if red, 2 if it cannot run. Runs pack-local evals/cases.yaml."""
    _run_gate(
        target=pack,
        skill=None,
        harness=harness,
        sandbox=sandbox,
        expect_fail=expect_fail,
        summary=summary,
        json_out=json_out,
        model=model,
        timeout=timeout,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        key_env=key_env,
        case_id=case_id,
        no_judge=no_judge,
        verbose=verbose,
    )


def run_suite(
    suite: Path = typer.Argument(..., help="Skill pack directory or eval suite YAML"),
    skill: Path | None = typer.Option(None, "--skill", help="Override the skill folder"),
    harness: str | None = typer.Option(None, "--harness", help=base._HARNESS_HELP),
    sandbox: str = typer.Option("local", "--sandbox", help=base._SANDBOX_HELP),
    expect_fail: bool = typer.Option(
        False,
        "--expect-fail",
        help="Exit 0 only if the suite is red (sabotaged / intentional-fail)",
    ),
    summary: str = typer.Option("cli", "--summary", help="cli | github | json"),
    json_out: bool = typer.Option(False, "--json", help="Machine JSON (not the primary UX)"),
    model: str | None = typer.Option(None, "--model", help="Requested model id"),
    timeout: int | None = typer.Option(None, "--timeout", help="Per-task timeout seconds"),
    temperature: float | None = typer.Option(None, "--temperature", help="Temperature (0–2)"),
    reasoning_effort: str | None = typer.Option(
        None, "--reasoning-effort", help="Reasoning effort: low | medium | high | ultra"
    ),
    key_env: list[str] | None = typer.Option(None, "--key-env", help=base._KEY_ENV_HELP),
) -> None:
    """Run an eval pack or suite YAML. Prefer `skillgate check` for CI."""
    notice = "Prefer `skillgate check` for CI."
    if json_out or summary == "json":
        sys.stderr.write(notice + "\n")
    else:
        base.console.print(notice)
    _run_gate(
        target=suite,
        skill=skill,
        harness=harness,
        sandbox=sandbox,
        expect_fail=expect_fail,
        summary=summary,
        json_out=json_out,
        model=model,
        timeout=timeout,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
        key_env=key_env,
    )
