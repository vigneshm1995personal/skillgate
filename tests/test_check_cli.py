from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from skillgate_ai.cli import _emit_json, app
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
    assert "scored this run" in result.stdout.lower()


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
    assert "built-in checker" not in result.stdout.lower()


def test_check_with_key_runs_live(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    class LiveStub:
        name = "llm"

        def run(self, *args, **kwargs):
            from skillgate_ai.errors import HarnessError

            raise HarnessError("live stub")

    monkeypatch.setattr(
        "skillgate_ai.gate.live_harness_or_error", lambda *a, **k: LiveStub()
    )
    result = runner.invoke(app, ["check", str(dest)])
    assert result.exit_code == 1, result.stdout
    assert "live stub" in result.stdout
    assert "built-in checker" not in result.stdout.lower()
    assert "GREEN" not in result.stdout


def test_check_demo_flag_forces_builtin_when_keys_set(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    result = runner.invoke(app, ["check", str(dest), "--demo"])
    assert result.exit_code == 0, result.stdout
    assert "GREEN" in result.stdout
    assert "built-in checker" in result.stdout.lower()
    assert "not a live model" in result.stdout.lower()


def test_emit_json_does_not_wrap_long_strings(capsys: pytest.CaptureFixture[str]) -> None:
    payload = {"note": "n" * 200, "ok": True}
    _emit_json(payload)
    raw = capsys.readouterr().out
    assert json.loads(raw) == payload
    assert "n" * 200 in raw


def test_check_json_is_parseable(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "40")
    _prepare(project_root)
    result = runner.invoke(app, ["check", str(project_root / "skills" / "pdf"), "--json"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload["gate"] == "green"
    assert payload["passed"] is True


def test_check_json_error_is_json(project_root: Path, tmp_path: Path) -> None:
    dest = tmp_path / "renamed"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    result = runner.invoke(app, ["check", str(dest), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert "must match the folder name" in str(payload.get("error") or "")
    assert payload.get("exit_code") == 1


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

