"""Claude Code harness: native Skill tool + `.claude/skills/` staging."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from test_judge import _cfg

from skillgate_ai.harness import (
    ClaudeCodeHarness,
    _infer_from_skill_tool,
    _resolve_trigger_evidence,
    claude_config_isolation_enabled,
    claude_native_skills_enabled,
)
from skillgate_ai.ingest import Skill
from skillgate_ai.sandbox import prepare_workspace
from skillgate_ai.spans import spans_from_jsonl


def test_claude_allowed_tools_include_skill() -> None:
    from skillgate_ai.harness import _claude_code_exec_command

    cmd = _claude_code_exec_command("/bin/claude", "task")
    tools = cmd[cmd.index("--allowedTools") + 1]
    assert "Skill" in tools


def test_prepare_workspace_stages_claude_native(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    pack.mkdir()
    (pack / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: PDF\n---\n# pdf\n", encoding="utf-8"
    )
    skill = Skill(path=pack, name="pdf", description="PDF", body="# pdf\n")
    ws = tmp_path / "ws"
    prepare_workspace(ws, [skill], [], stage_claude_native=True)
    assert (ws / ".skillgate" / "skills" / "pdf" / "SKILL.md").is_file()
    assert (ws / ".claude" / "skills" / "pdf" / "SKILL.md").is_file()


def test_claude_native_skills_opt_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_CLAUDE_NATIVE_SKILLS", "0")
    assert claude_native_skills_enabled() is False
    monkeypatch.delenv("SKILLGATE_CLAUDE_NATIVE_SKILLS", raising=False)
    assert claude_native_skills_enabled() is True


def test_skill_tool_call_detected_as_load(tmp_path: Path) -> None:
    skill = Skill(path=tmp_path / "pdf", name="pdf", description="PDF", body="#")
    line = json.dumps(
        {
            "type": "tool_call",
            "subtype": "started",
            "tool_call": {
                "skillToolCall": {"args": {"skill": "pdf"}},
            },
        }
    )
    assert _infer_from_skill_tool(line, [skill]) == "pdf"
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".claude" / "skills" / "pdf").mkdir(parents=True)
    (ws / ".claude" / "skills" / "pdf" / "SKILL.md").write_text("x", encoding="utf-8")
    selected, paths = _resolve_trigger_evidence(
        ws,
        "",
        [skill],
        stdout=line,
        spans=spans_from_jsonl(line),
    )
    assert selected == "pdf"
    assert any("pdf" in path for path in paths)


def test_claude_harness_preserves_host_config_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}

    class _Sandbox:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def run(self, command, *, env=None, timeout=0, cwd=None):
            seen["env"] = dict(env or {})
            seen["command"] = list(command)
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.delenv("SKILLGATE_CLAUDE_ISOLATE_CONFIG", raising=False)
    assert claude_config_isolation_enabled() is False
    monkeypatch.setattr("skillgate_ai.harness.auth._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness.bins._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setattr(
        "skillgate_ai.harness.selection._resolve_trigger_evidence", lambda *a, **k: (None, [])
    )
    monkeypatch.setattr("skillgate_ai.harness.selection._write_selection", lambda *a: None)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ClaudeCodeHarness(_cfg(anthropic_api_key="ant-test")).run(
        _Sandbox(workspace),  # type: ignore[arg-type]
        "Do the task.",
        [],
        timeout_sec=5,
    )
    env = seen["env"]
    assert isinstance(env, dict)
    assert "HOME" not in env
    assert "CLAUDE_CONFIG_DIR" not in env
    assert env.get("CLAUDE_CODE_DISABLE_BUNDLED_SKILLS") == "1"
    command = seen["command"]
    assert isinstance(command, list)
    tools = command[command.index("--allowedTools") + 1]
    assert "Skill" in tools


def test_claude_config_isolation_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    class _Sandbox:
        def __init__(self, workspace: Path) -> None:
            self.workspace = workspace

        def run(self, command, *, env=None, timeout=0, cwd=None):
            seen["env"] = dict(env or {})
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setenv("SKILLGATE_CLAUDE_ISOLATE_CONFIG", "1")
    assert claude_config_isolation_enabled() is True
    monkeypatch.setattr("skillgate_ai.harness.auth._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness.bins._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setattr(
        "skillgate_ai.harness.selection._resolve_trigger_evidence", lambda *a, **k: (None, [])
    )
    monkeypatch.setattr("skillgate_ai.harness.selection._write_selection", lambda *a: None)
    workspace = tmp_path / "ws"
    workspace.mkdir()
    ClaudeCodeHarness(_cfg()).run(
        _Sandbox(workspace),  # type: ignore[arg-type]
        "task",
        [],
        timeout_sec=5,
    )
    env = seen["env"]
    assert str(tmp_path) in str(env.get("HOME"))
    assert str(tmp_path) in str(env.get("CLAUDE_CONFIG_DIR"))
