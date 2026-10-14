"""Agent harness selection: Cursor, Codex, Claude Code only — no LLM fallback."""

from __future__ import annotations

import pytest

from skillgate_ai.config import LLMConfig, missing_key_error, no_agent_available_error
from skillgate_ai.harness import (
    ClaudeCodeHarness,
    CodexCliHarness,
    CursorAgentHarness,
    _claude_code_exec_command,
    _codex_exec_command,
    live_harness_or_error,
)
from skillgate_ai.errors import HarnessError, MissingLLMKeyError
from test_judge import _cfg


def test_auto_prefers_cursor_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    cfg = _cfg(cursor_api_key="cur-test", codex_api_key="codex-test")
    harness = live_harness_or_error("auto", cfg)
    assert isinstance(harness, CursorAgentHarness)


def test_auto_uses_codex_when_cursor_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    cfg = _cfg(codex_api_key="codex-test")
    harness = live_harness_or_error("auto", cfg)
    assert isinstance(harness, CodexCliHarness)


def test_auto_uses_claude_when_only_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    cfg = _cfg(anthropic_api_key="ant-test")
    harness = live_harness_or_error("auto", cfg)
    assert isinstance(harness, ClaudeCodeHarness)


def test_openai_key_does_not_select_llm_harness(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: None)
    cfg = _cfg(openai_api_key="sk-test", gateway_api_key="gw-test")
    with pytest.raises(MissingLLMKeyError) as caught:
        live_harness_or_error("auto", cfg)
    assert "No agent is available" in caught.value.message
    assert "skillgate keys set" in (caught.value.hint or "")


def test_no_agent_error_is_actionable() -> None:
    err = no_agent_available_error(_cfg())
    assert err.exit_code == 2
    assert "CURSOR_API_KEY" in (err.hint or "")
    assert "CODEX_API_KEY" in (err.hint or "")
    assert "ANTHROPIC_API_KEY" in (err.hint or "")


def test_removed_llm_harness_errors() -> None:
    with pytest.raises(HarnessError) as caught:
        live_harness_or_error("llm", _cfg(openai_api_key="sk-test"))
    assert "removed" in caught.value.message.lower()


def test_claude_harness_skips_permissions_headless() -> None:
    cmd = _claude_code_exec_command("/bin/claude", "run task")
    assert "--dangerously-skip-permissions" in cmd
    assert "acceptEdits" not in cmd


def test_codex_harness_approves_headless() -> None:
    cmd = _codex_exec_command("/bin/codex", "/tmp/ws", "run task")
    assert "--approve-for-me" in cmd


def test_user_pdf_skill_name_does_not_require_seed_cases(tmp_path) -> None:
    from skillgate_ai.case_pack import CasePack, PackCase, save_case_pack
    from skillgate_ai.pack_schema import reject_missing_seed_cases

    dest = tmp_path / "pdf"
    dest.mkdir()
    (dest / "SKILL.md").write_text("---\nname: pdf\ndescription: d\n---\n# pdf\n", encoding="utf-8")
    pack = CasePack(schema_version=1, skill="pdf", cases=[])
    reject_missing_seed_cases(pack.skill, [])
    save_case_pack(dest, pack)
