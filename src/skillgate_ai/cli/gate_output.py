"""CLI gate output helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NoReturn

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.api_payloads import scrub_browser_payload
from skillgate_ai.errors import SkillGateError
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
