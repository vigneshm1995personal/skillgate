from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from skillgate_ai.config import get_llm_config
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.gate import run_check
from skillgate_ai.harness import DemoHarness, resolve_harness


def test_gate_matches_cli_exits(project_root: Path) -> None:
    pdf = project_root / "skills" / "pdf"
    sabotaged = project_root / "skills" / "pdf-sabotaged"
    ensure_demo_pdfs(pdf / "evals" / "fixtures")
    ensure_demo_pdfs(sabotaged / "evals" / "fixtures")

    green = run_check(pdf, source="test", root=project_root)
    assert green.exit_code == 0
    assert green.report is not None and green.report.passed

    red = run_check(sabotaged, source="test", root=project_root)
    assert red.exit_code == 1
    assert red.report is not None and not red.report.passed

    expected = run_check(sabotaged, expect_fail=True, source="test", root=project_root)
    assert expected.exit_code == 0
    assert expected.expect_fail_notice

    live = run_check(pdf, live=True, source="test", root=project_root)
    assert live.exit_code == 2
    assert live.error is not None
    assert "No model key" in (live.error.get("message") or "")


def _stub_missing_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("CODEX_API_KEY", "sk-codex-not-a-real-key")
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _preferred: None)


def test_auto_falls_back_to_demo_when_codex_binary_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_missing_codex(monkeypatch)
    cfg = get_llm_config()
    assert cfg.codex_api_key
    harness = resolve_harness("auto", cfg)
    assert isinstance(harness, DemoHarness)


def test_run_check_pdf_stays_green_when_codex_env_but_no_binary(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_missing_codex(monkeypatch)
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    result = run_check(dest, source="test", root=project_root)
    assert result.exit_code == 0, result.error
    assert result.report is not None
    assert result.report.harness == "demo"
    assert result.report.passed
    assert len(result.report.tasks) > 0
    assert result.demo_notice
    assert "demo harness" in result.demo_notice.lower()


def test_live_does_not_demo_fallback_when_codex_missing(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_missing_codex(monkeypatch)
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    result = run_check(dest, live=True, source="test", root=project_root)
    assert result.exit_code != 0
    assert result.report is None
    assert result.error is not None
