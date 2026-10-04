from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from skillgate_ai.config import get_llm_config
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.gate import run_check
from skillgate_ai.harness import DemoHarness, live_harness_or_error, resolve_harness


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


def test_resolve_harness_auto_stays_demo_when_keys_are_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """resolve_harness('auto') is demo. Gate uses live_harness_or_error when a key is present."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-test-not-a-real-key")
    monkeypatch.setenv("CODEX_API_KEY", "sk-codex-not-a-real-key")
    cfg = get_llm_config()
    assert cfg.has_any_key
    assert isinstance(resolve_harness("auto", cfg), DemoHarness)


def test_run_check_uses_live_when_key_present(
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
    result = run_check(dest, source="test", root=project_root)
    assert result.exit_code == 1
    assert result.demo_notice is None
    assert result.error is not None
    assert "live stub" in (result.error.get("message") or "")


def test_run_check_demo_flag_forces_builtin_when_keys_set(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-test-not-a-real-key")
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    result = run_check(dest, demo=True, source="test", root=project_root)
    assert result.exit_code == 0, result.error
    assert result.report is not None
    assert result.report.harness == "demo"
    assert result.report.passed
    assert result.demo_notice
    assert "built-in checker" in result.demo_notice.lower()
    assert "not a live model" in result.demo_notice.lower()


def test_live_auto_uses_gateway_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AI_GATEWAY_API_KEY", "gw-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _preferred: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _preferred: None)
    cfg = get_llm_config()
    harness = live_harness_or_error("auto", cfg)
    assert harness.name == "llm"


def test_live_flag_does_not_fall_back_to_demo(
    project_root: Path, tmp_path: Path
) -> None:
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    result = run_check(dest, live=True, demo=True, source="test", root=project_root)
    assert result.exit_code == 2
    assert result.report is None
    assert result.demo_notice is None
    assert result.error is not None


def test_live_flag_with_key_ignores_demo(
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
    result = run_check(dest, live=True, demo=True, source="test", root=project_root)
    assert result.exit_code == 1
    assert result.report is None
    assert result.demo_notice is None
    assert result.error is not None
    assert "live stub" in (result.error.get("message") or "")


def test_live_without_key_still_errors(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _preferred: None)
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    result = run_check(dest, live=True, source="test", root=project_root)
    assert result.exit_code == 2
    assert result.report is None
    assert result.error is not None
