"""Fresh-env round 3 (PR #23 follow-up)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from conftest import plain_text
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.history import append_eval

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[1]


def test_bundle_web_static_invokes_pnpm_with_cwd_web_dir(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location("skillgate_build", ROOT / "src" / "skillgate_build.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    web_dir = tmp_path / "web"
    web_dir.mkdir()
    (web_dir / "package.json").write_text('{"packageManager":"pnpm@9.15.9"}\n', encoding="utf-8")
    dist = web_dir / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<html></html>\n", encoding="utf-8")
    calls: list[tuple[list[str], dict]] = []

    def fake_check_call(cmd, **kwargs):
        calls.append((list(cmd), kwargs))

    with patch("subprocess.check_call", side_effect=fake_check_call):
        with patch("shutil.which", return_value="/usr/bin/pnpm"):
            module.bundle_web_static(
                dest=tmp_path / "out",
                web_dist=dist,
                web_dir=web_dir,
            )
    assert calls, "expected pnpm install/build"
    install_cmd, install_kw = calls[0]
    assert install_kw.get("cwd") == web_dir.resolve()
    assert "--dir" not in install_cmd
    assert install_cmd[:2] == ["/usr/bin/pnpm", "install"]


@pytest.mark.slow
def test_pip_install_sdist_succeeds_in_clean_home(tmp_path: Path) -> None:
    """Git/source installs must not require a global pnpm when corepack would pick v12."""
    home = tmp_path / "home"
    home.mkdir()
    env = os.environ.copy()
    env["HOME"] = str(home)
    env.pop("PNPM_HOME", None)
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")
    build_dir = tmp_path / "build"
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "build", "-q"],
        env=env,
        cwd=ROOT,
    )
    subprocess.check_call(
        [sys.executable, "-m", "build", "--sdist", "-o", str(build_dir)],
        env=env,
        cwd=ROOT,
    )
    sdist = next(build_dir.glob("skillgate_ai-*.tar.gz"), None)
    assert sdist is not None
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", str(sdist), "-q"],
        env=env,
        cwd=ROOT,
    )


def test_compare_versions_bare_dry_run_lists_choices(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    append_eval(
        pack,
        run_id="run-aaaa1111",
        passed=True,
        report={"tasks": [{"id": "c1", "passed": True}], "task_count": 1, "passed_count": 1},
    )
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["compare", "versions", str(pack), "--dry-run"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "run-aaaa1111" in out
    assert "Pick two" in out or "recent" in out.lower()


def test_compare_models_dry_run_shows_arm_models(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(
        app,
        [
            "compare",
            "models",
            str(pack),
            "--arm",
            "A:llm:openai/gpt-4o-mini",
            "--arm",
            "B:llm:openai/gpt-4o",
            "--dry-run",
        ],
    )
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "gpt-4o-mini" in out
    assert "gpt-4o" in out


def test_history_show_prints_run_error_reason(tmp_path: Path, monkeypatch) -> None:
    pack = tmp_path / "skills" / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    append_eval(
        pack,
        run_id="err-run-01",
        passed=False,
        report={
            "tasks": [{"id": "c1", "passed": False, "failures": ["Expected output missing."]}],
            "task_count": 1,
            "passed_count": 0,
        },
        error={"message": "Check run failed.", "hint": "Fix the skill."},
    )
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    result = runner.invoke(app, ["history", "show", "err-run-01", "--pack", str(pack)])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert "Check run failed." in out
    assert "Expected output missing." in out


def test_check_help_hides_docker_sandbox_option() -> None:
    result = runner.invoke(app, ["check", "--help"])
    out = plain_text(result.stdout + result.stderr)
    collapsed = " ".join(out.split())
    assert "--sandbox" in collapsed
    assert "docker" not in collapsed.lower()


def test_root_package_json_pins_pnpm_nine() -> None:
    root_pkg = ROOT / "package.json"
    assert root_pkg.is_file()
    text = root_pkg.read_text(encoding="utf-8")
    assert "pnpm@9" in text
