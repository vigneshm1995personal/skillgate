"""First-time-user QA: compare dry-run hint and judge provider show when unset."""

from __future__ import annotations

import shutil
from pathlib import Path

from conftest import ROOT, plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app

runner = CliRunner()


def test_compare_versions_dry_run_without_refs_prints_hint(
    tmp_path: Path, monkeypatch
) -> None:
    pack = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["compare", "versions", str(pack), "--dry-run"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "--run" in out
    assert "--git" in out
    assert "two" in out.lower()
    assert "Checks" not in out


def test_judge_provider_show_without_model_exits_nonzero(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["judge", "provider", "show"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code != 0, out
    assert "Pick a decision model" in out
    assert "judge provider set" in out
