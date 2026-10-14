from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from skillgate_ai.config import get_llm_config
from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.gate import run_check
from skillgate_ai.harness import CursorAgentHarness, live_harness_or_error
from skillgate_ai.keys import set_vault_key
from skillgate_ai.paths import resolve_user_path


def test_gate_without_key_exits_2(project_root: Path) -> None:
    pdf = project_root / "skills" / "pdf"
    ensure_demo_pdfs(pdf / "evals" / "fixtures")
    result = run_check(pdf, source="test", root=project_root)
    assert result.exit_code == 2
    assert result.report is None
    assert result.error is not None
    assert "No agent is available" in (result.error.get("message") or "")
    hint = result.error.get("hint") or ""
    assert "skillgate keys set" in hint
    assert "SKILLGATE_" not in hint
    assert "--key-env" not in hint


def test_ambient_key_does_not_start_a_check(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    result = run_check(dest, source="test", root=tmp_path)
    assert result.exit_code == 2
    assert result.report is None


def test_run_check_uses_live_when_key_present(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("SKILLGATE_OPENAI_API_KEY", "sk-test-not-a-real-key")
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    class LiveStub:
        name = "llm"

        def run(self, *args, **kwargs):
            from skillgate_ai.errors import HarnessError

            raise HarnessError("live stub")

    monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *a, **k: LiveStub())
    result = run_check(dest, source="test", root=tmp_path)
    assert result.exit_code == 1
    assert result.demo_notice is None
    assert result.error is not None
    assert "live stub" in (result.error.get("message") or "")


def test_live_auto_uses_cursor_when_vault_has_cursor_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    set_vault_key(tmp_path, "CURSOR_API_KEY", "cur-from-vault")
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _preferred: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _preferred: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _preferred: "/bin/agent")
    cfg = get_llm_config(tmp_path)
    harness = live_harness_or_error("auto", cfg)
    assert isinstance(harness, CursorAgentHarness)
    assert harness.name == "cursor-agent"


def test_vault_openai_key_does_not_start_checks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    set_vault_key(tmp_path, "OPENAI_API_KEY", "sk-from-vault")
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _preferred: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _preferred: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _preferred: None)
    cfg = get_llm_config(tmp_path)
    assert cfg.openai_api_key == "sk-from-vault"
    assert cfg.has_any_key is False


def test_openai_judge_without_scoring_key_exits_2(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_JUDGE", "openai")
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    from conftest import enable_cursor_agent

    enable_cursor_agent(monkeypatch, tmp_path)
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    class LiveStub:
        name = "cursor-agent"

        def run(self, *args, **kwargs):
            raise AssertionError("live harness should not run without a scoring key")

    monkeypatch.setattr("skillgate_ai.gate.live_harness_or_error", lambda *a, **k: LiveStub())
    result = run_check(dest, source="test", root=tmp_path)
    assert result.exit_code == 2
    assert result.report is None
    assert result.error is not None
    assert "OpenAI" in (result.error.get("message") or "")
    blob = json.dumps(result.error)
    assert "sk-" not in blob


def test_live_without_key_still_errors(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _preferred: None)
    dest = tmp_path / "pdf"
    shutil.copytree(project_root / "skills" / "pdf", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")

    result = run_check(dest, source="test", root=tmp_path)
    assert result.exit_code == 2
    assert result.report is None
    assert result.error is not None


def test_resolve_user_path_prefers_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proj = tmp_path / "proj"
    work = proj / "work"
    work.mkdir(parents=True)
    local = work / "pdf"
    local.mkdir()
    (local / "SKILL.md").write_text("---\nname: pdf\n---\n", encoding="utf-8")
    other = proj / "pdf"
    other.mkdir()
    (other / "SKILL.md").write_text("---\nname: other\n---\n", encoding="utf-8")
    monkeypatch.chdir(work)
    resolved = resolve_user_path(Path("./pdf"), proj)
    assert resolved == local.resolve()
    via_name = resolve_user_path(Path("pdf"), proj)
    assert via_name == local.resolve()
