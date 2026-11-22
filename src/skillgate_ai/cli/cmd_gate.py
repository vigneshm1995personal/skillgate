"""CLI commands."""

from __future__ import annotations

import sys
from pathlib import Path

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.cli.gate_output import _exit_with_error, _finish_gate
from skillgate_ai.errors import SkillGateError, timeout_harness_error
from skillgate_ai.gate import run_check
from skillgate_ai.paths import project_root, resolve_user_path


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
