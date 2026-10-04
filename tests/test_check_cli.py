from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.demo_files import ensure_demo_pdfs

runner = CliRunner()


def _prepare(project_root: Path) -> None:
    for name in ("pdf", "pdf-sabotaged"):
        pack = project_root / "skills" / name
        ensure_demo_pdfs(pack / "evals" / "fixtures")


def test_check_pdf_green(project_root: Path) -> None:
    _prepare(project_root)
    result = runner.invoke(app, ["check", str(project_root / "skills" / "pdf")])
    assert result.exit_code == 0, result.stdout
    assert "GREEN" in result.stdout
    assert "built-in checker" in result.stdout.lower()
    assert "not a live model" in result.stdout.lower()


def test_check_sabotaged_red(project_root: Path) -> None:
    _prepare(project_root)
    result = runner.invoke(app, ["check", str(project_root / "skills" / "pdf-sabotaged")])
    assert result.exit_code == 1, result.stdout
    assert "RED" in result.stdout
    assert "Corrected SKILL.md description" in result.stdout
    paste_part = result.stdout.split("Corrected SKILL.md description")[-1].lower()
    assert "grocery" not in paste_part
    assert "dinner" not in paste_part


def test_check_expect_fail_on_sabotaged(project_root: Path) -> None:
    _prepare(project_root)
    result = runner.invoke(
        app, ["check", str(project_root / "skills" / "pdf-sabotaged"), "--expect-fail"]
    )
    assert result.exit_code == 0, result.stdout
    assert "expected" in result.stdout.lower()


def test_check_live_without_key_errors(project_root: Path) -> None:
    _prepare(project_root)
    result = runner.invoke(
        app, ["check", str(project_root / "skills" / "pdf"), "--live"]
    )
    assert result.exit_code == 2
    assert "No model key" in result.stdout


def test_no_serve_command() -> None:
    result = runner.invoke(app, ["serve"])
    assert result.exit_code != 0
    assert "No such command" in (result.stdout + result.stderr) or "Got unexpected extra argument" in (
        result.stdout + result.stderr
    ) or "No such command 'serve'" in (result.stdout + result.stderr)


def test_ui_help() -> None:
    result = runner.invoke(app, ["ui", "--help"])
    assert result.exit_code == 0, result.stdout
    combined = result.stdout + result.stderr
    assert "127.0.0.1" in combined
    assert "no account" in combined.lower()
    assert "8765" in combined

