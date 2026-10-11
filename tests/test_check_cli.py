from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import plain_text
from skillgate_ai.cli import _emit_json, app
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.deploy import latest_check_passed

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
    result = runner.invoke(app, ["check", str(project_root / "skills" / "pdf"), "--live"])
    assert result.exit_code == 2
    assert "No model key" in result.stdout
    assert "built-in checker" not in result.stdout.lower()
    assert "BYOLLM" not in result.stdout
    assert "BYO LLM" not in result.stdout


def test_live_missing_key_is_not_recorded_as_failed_check(
    project_root: Path, tmp_path: Path
) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", pack)
    ensure_demo_pdfs(pack / "evals" / "fixtures")
    hist = pack / "evals" / "history"
    if hist.is_dir():
        for path in hist.glob("*.jsonl"):
            path.unlink()
    assert latest_check_passed(pack) is None
    result = runner.invoke(app, ["check", str(pack), "--live"])
    assert result.exit_code == 2
    assert "No model key" in result.stdout
    assert latest_check_passed(pack) is None
    assert not hist.exists() or not any(hist.glob("*.jsonl"))


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

    monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *a, **k: LiveStub())
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
    assert payload["scored_by"] == ("Built-in checker scored this run. This is not a live model.")


def test_check_json_error_is_json(project_root: Path, tmp_path: Path) -> None:
    dest = tmp_path / "renamed"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    result = runner.invoke(app, ["check", str(dest), "--json"])
    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert "must match the folder name" in str(payload.get("error") or "")
    assert payload.get("exit_code") == 1


def test_run_prints_prefer_check_hint(project_root: Path) -> None:
    _prepare(project_root)
    result = runner.invoke(app, ["run", str(project_root / "skills" / "pdf"), "--demo"])
    combined = result.stdout + result.stderr
    assert "Prefer `skillgate check`" in combined
    assert result.exit_code == 0, combined


def test_no_serve_command() -> None:
    result = runner.invoke(app, ["serve"])
    assert result.exit_code != 0
    assert (
        "No such command" in (result.stdout + result.stderr)
        or "Got unexpected extra argument" in (result.stdout + result.stderr)
        or "No such command 'serve'" in (result.stdout + result.stderr)
    )


def test_reasoning_effort_silly_is_rejected(project_root: Path) -> None:
    _prepare(project_root)
    result = runner.invoke(
        app,
        ["check", str(project_root / "skills" / "pdf"), "--demo", "--reasoning-effort", "silly"],
    )
    assert result.exit_code == 2, result.stdout
    combined = result.stdout + result.stderr
    assert "low, medium, high, or ultra" in combined
    assert "Traceback" not in combined


def test_check_relative_pack_from_subfolder(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    work = proj / "work"
    work.mkdir(parents=True)
    shutil.copytree(project_root / "skills" / "pdf", work / "pdf")
    skills = proj / "skills"
    skills.mkdir()
    shutil.copytree(project_root / "skills" / "pdf", skills / "pdf")
    monkeypatch.chdir(work)
    monkeypatch.setenv("SKILLGATE_ROOT", str(proj))
    result = runner.invoke(app, ["check", "./pdf", "--demo"])
    assert result.exit_code == 0, result.stdout
    assert "GREEN" in result.stdout


def test_sabotaged_reasons_are_per_task(project_root: Path) -> None:
    _prepare(project_root)
    result = runner.invoke(app, ["check", str(project_root / "skills" / "pdf-sabotaged"), "--demo"])
    assert result.exit_code == 1, result.stdout
    lower = result.stdout.lower()
    assert "rotate-hello" in lower
    assert "merge-alpha-beta" in lower
    rotate_idx = result.stdout.index("rotate-hello")
    merge_idx = result.stdout.index("merge-alpha-beta")
    hello = "Extract the text from hello.pdf"
    # The first failed case may quote hello.pdf; later cases must not reuse it.
    after_rotate = result.stdout[rotate_idx : rotate_idx + 500]
    after_merge = result.stdout[merge_idx : merge_idx + 500]
    assert hello not in after_rotate
    assert hello not in after_merge
    assert "Skill didn’t trigger" not in after_rotate
    assert "Skill didn't trigger" not in after_rotate


def test_ui_help() -> None:
    result = runner.invoke(app, ["ui", "--help"], color=False)
    assert result.exit_code == 0, result.stdout
    combined = plain_text(result.stdout + result.stderr)
    assert "127.0.0.1" in combined
    assert "no account" in combined.lower()
    assert "8765" in combined
