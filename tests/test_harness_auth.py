"""Auth resolution: API key vs CLI login vs none, for Cursor, Codex, and Claude Code."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from conftest import plain_text
from test_judge import _cfg
from typer.testing import CliRunner

from skillgate_ai.cli import app
from skillgate_ai.config import missing_key_error, no_agent_available_error
from skillgate_ai.errors import HarnessError
from skillgate_ai.harness import (
    AUTH_API_KEY,
    AUTH_CLI_LOGIN,
    AUTH_NONE,
    ClaudeCodeHarness,
    CodexCliHarness,
    CursorAgentHarness,
    _claude_login_status_authenticated,
    _codex_exec_command,
    _codex_login_status_authenticated,
    _codex_model_flag,
    _codex_rejected_model,
    _codex_used_model,
    _cursor_exec_command,
    _cursor_login_status_authenticated,
    _login_timeout_sec,
    _resolve_agent_bin,
    _run_inherited,
    claude_auth_kind,
    codex_auth_kind,
    codex_chatgpt_model_hint,
    cursor_auth_kind,
    harness_auth_status,
    harness_is_startable,
    has_startable_agent,
    live_harness_or_error,
    run_official_login,
)
from skillgate_ai.usage import SUBSCRIPTION_COST_LABEL, combine_task_usage


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return False
    stat = Path(f"/proc/{pid}/stat")
    if stat.is_file():
        try:
            tail = stat.read_text(encoding="utf-8").rsplit(")", 1)
            if len(tail) > 1 and tail[1].split()[0] == "Z":
                return False
        except OSError:
            pass
    return True


def _pid_gone(pid: int, *, timeout: float = 5.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if not _pid_alive(pid):
            return True
        time.sleep(0.05)
    return False


class _FakeSandbox:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.env: dict[str, str] = {}
        self.command: list[str] = []

    def run(self, command, *, env=None, timeout=0, cwd=None):
        self.command = list(command)
        self.env = dict(env or {})
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")


def _stub_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._read_selection", lambda _w: "pdf")
    monkeypatch.setattr("skillgate_ai.harness._parse_selected", lambda *a: "pdf")
    monkeypatch.setattr("skillgate_ai.harness._parse_read_paths", lambda _t: [])
    monkeypatch.setattr("skillgate_ai.harness._write_selection", lambda *a: None)


def test_cursor_auth_kind_key_login_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda _c: False)
    assert cursor_auth_kind(_cfg(cursor_api_key="cur-test")) == AUTH_API_KEY
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda _c: True)
    assert cursor_auth_kind(_cfg(cursor_api_key=None)) == AUTH_CLI_LOGIN
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda _c: False)
    assert cursor_auth_kind(_cfg(cursor_api_key=None)) == AUTH_NONE


def test_codex_auth_kind_key_login_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._codex_session_ok", lambda _c: False)
    assert codex_auth_kind(_cfg(codex_api_key="codex-test")) == AUTH_API_KEY
    monkeypatch.setattr("skillgate_ai.harness._codex_session_ok", lambda _c: True)
    assert codex_auth_kind(_cfg(codex_api_key=None)) == AUTH_CLI_LOGIN
    monkeypatch.setattr("skillgate_ai.harness._codex_session_ok", lambda _c: False)
    assert codex_auth_kind(_cfg(codex_api_key=None)) == AUTH_NONE


def test_claude_auth_kind_key_login_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._claude_session_ok", lambda _c: False)
    assert claude_auth_kind(_cfg(anthropic_api_key="ant-test")) == AUTH_API_KEY
    monkeypatch.setattr("skillgate_ai.harness._claude_session_ok", lambda _c: True)
    assert claude_auth_kind(_cfg(anthropic_api_key=None)) == AUTH_CLI_LOGIN
    monkeypatch.setattr("skillgate_ai.harness._claude_session_ok", lambda _c: False)
    assert claude_auth_kind(_cfg(anthropic_api_key=None)) == AUTH_NONE


def test_key_wins_over_cli_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._codex_session_ok", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._claude_session_ok", lambda _c: True)
    assert cursor_auth_kind(_cfg(cursor_api_key="cur-test")) == AUTH_API_KEY
    assert codex_auth_kind(_cfg(codex_api_key="codex-test")) == AUTH_API_KEY
    assert claude_auth_kind(_cfg(anthropic_api_key="ant-test")) == AUTH_API_KEY


# Claude Code 2.1.302 `claude auth status` JSON (subscription login). Email is
# fixture data only; parsers and login results must never echo it.
_CLAUDE_AUTH_STATUS_LOGGED_IN = {
    "analyticsDisabled": False,
    "apiProvider": "firstParty",
    "authMethod": "claude.ai",
    "configDirectory": "/tmp/skillgate-test-home/.claude",
    "email": "user@example.com",
    "loggedIn": True,
    "orgId": "org-test-id",
    "orgName": "Example Org",
    "projectsDirectory": "/tmp/skillgate-test-home/.claude/projects",
    "subscriptionType": "pro",
}
_CLAUDE_AUTH_STATUS_LOGGED_OUT = {
    "analyticsDisabled": False,
    "apiProvider": "firstParty",
    "authMethod": "none",
    "configDirectory": "/tmp/skillgate-test-home/.claude",
    "email": None,
    "loggedIn": False,
    "orgId": None,
    "orgName": None,
    "projectsDirectory": "/tmp/skillgate-test-home/.claude/projects",
    "subscriptionType": None,
}


def _isolate_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    return home


def test_login_status_parsers() -> None:
    assert _cursor_login_status_authenticated(0, "Logged in as user\n", "")
    assert not _cursor_login_status_authenticated(1, "Logged in", "")
    assert not _cursor_login_status_authenticated(0, "Not logged in", "")
    assert _codex_login_status_authenticated(0, "Logged in using ChatGPT\n", "")
    assert not _codex_login_status_authenticated(1, "Logged in", "")
    assert not _codex_login_status_authenticated(0, "Not logged in", "")
    assert _claude_login_status_authenticated(0, "Logged in as user@example.com\n", "")
    assert not _claude_login_status_authenticated(1, "Logged in", "")
    assert not _claude_login_status_authenticated(0, "Not logged in", "")
    assert not _claude_login_status_authenticated(0, "Not authenticated", "")


def test_claude_auth_status_json_logged_in() -> None:
    stdout = json.dumps(_CLAUDE_AUTH_STATUS_LOGGED_IN, indent=2) + "\n"
    assert "logged in" not in stdout.lower()
    assert _claude_login_status_authenticated(0, stdout, "")
    assert not _claude_login_status_authenticated(1, stdout, "")


def test_claude_auth_status_json_logged_out() -> None:
    stdout = json.dumps(_CLAUDE_AUTH_STATUS_LOGGED_OUT, indent=2) + "\n"
    assert not _claude_login_status_authenticated(0, stdout, "")
    assert not _claude_login_status_authenticated(1, stdout, "")


def test_login_claude_succeeds_when_auth_status_json_logged_in(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    home = _isolate_home(monkeypatch, tmp_path)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setattr("skillgate_ai.harness._run_inherited", lambda _argv, timeout=None: 0)

    def fake_run(argv, **_kwargs):
        assert argv[:3] == ["/bin/claude", "auth", "status"]
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout=json.dumps(_CLAUDE_AUTH_STATUS_LOGGED_IN, indent=2) + "\n",
            stderr="",
        )

    monkeypatch.setattr("skillgate_ai.harness.subprocess.run", fake_run)
    result = run_official_login("claude", _cfg(anthropic_api_key=None))
    assert result["ok"] is True
    assert result["status"] == "logged in"
    blob = json.dumps(result)
    assert "user@example.com" not in blob
    assert "token" not in blob.lower()
    assert list(home.iterdir()) == []


def test_auto_picks_claude_when_cli_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setattr("skillgate_ai.harness._claude_session_ok", lambda _c: True)
    harness = live_harness_or_error("auto", _cfg(anthropic_api_key=None))
    assert isinstance(harness, ClaudeCodeHarness)


def test_auto_picks_codex_when_cli_logged_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    monkeypatch.setattr("skillgate_ai.harness._codex_session_ok", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: None)
    harness = live_harness_or_error("auto", _cfg(codex_api_key=None))
    assert isinstance(harness, CodexCliHarness)


def test_claude_startable_with_cli_login(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setattr("skillgate_ai.harness._claude_session_ok", lambda _c: True)
    cfg = _cfg(anthropic_api_key=None)
    assert harness_is_startable(ClaudeCodeHarness(cfg), cfg)


def test_claude_run_omits_empty_key_when_cli_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox = _FakeSandbox(tmp_path)
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    result = ClaudeCodeHarness(_cfg(anthropic_api_key=None)).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert "ANTHROPIC_API_KEY" not in sandbox.env
    assert sandbox.env.get("HOME") is None
    assert result.auth_mode == AUTH_CLI_LOGIN


def test_claude_run_injects_key_when_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox = _FakeSandbox(tmp_path)
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    result = ClaudeCodeHarness(_cfg(anthropic_api_key="ant-secret")).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert sandbox.env["ANTHROPIC_API_KEY"] == "ant-secret"
    assert result.auth_mode == AUTH_API_KEY


def test_claude_run_omits_model_flag_by_default(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox = _FakeSandbox(tmp_path)
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    result = ClaudeCodeHarness(_cfg(anthropic_api_key=None, anthropic_model="")).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert "--model" not in sandbox.command
    assert result.model is None


def test_claude_run_passes_model_flag_when_chosen(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox = _FakeSandbox(tmp_path)
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    ClaudeCodeHarness(_cfg(anthropic_api_key=None, anthropic_model="sonnet")).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert "--model" in sandbox.command
    assert sandbox.command[sandbox.command.index("--model") + 1] == "sonnet"


def _claude_jsonl(lines: list[dict]) -> str:
    return "".join(json.dumps(line) + "\n" for line in lines)


def _claude_sandbox_run(stdout: str) -> _FakeSandbox:
    sandbox = _FakeSandbox(Path("/tmp/ws"))

    def run(command, *, env=None, timeout=0, cwd=None):
        sandbox.command = list(command)
        sandbox.env = dict(env or {})
        return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")

    sandbox.run = run  # type: ignore[method-assign]
    return sandbox


def test_claude_run_resolves_alias_to_model_usage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = _claude_sandbox_run(
        _claude_jsonl(
            [
                {"type": "system", "model": "claude-sonnet-5-5"},
                {
                    "type": "result",
                    "subtype": "success",
                    "result": "done",
                    "modelUsage": {"claude-sonnet-5-5": {"inputTokens": 1, "outputTokens": 1}},
                },
            ]
        )
    )
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    result = ClaudeCodeHarness(_cfg(anthropic_api_key=None, anthropic_model="sonnet")).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert "--model" in sandbox.command
    assert sandbox.command[sandbox.command.index("--model") + 1] == "sonnet"
    assert result.model == "claude-sonnet-5-5"


def test_claude_run_parses_model_from_result_model_usage(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _claude_sandbox_run(
        _claude_jsonl(
            [
                {"type": "system", "model": "claude-opus-5-5"},
                {
                    "type": "result",
                    "subtype": "success",
                    "result": "done",
                    "modelUsage": {"claude-opus-5-5": {"inputTokens": 1, "outputTokens": 1}},
                },
            ]
        )
    )
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    result = ClaudeCodeHarness(_cfg(anthropic_api_key=None, anthropic_model="")).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert result.model == "claude-opus-5-5"


def test_claude_run_parses_model_from_system_init_fallback(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _claude_sandbox_run(
        _claude_jsonl(
            [
                {"type": "system", "model": "claude-sonnet-5-5"},
                {"type": "assistant", "message": {"content": [{"type": "text", "text": "hi"}]}},
            ]
        )
    )
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    result = ClaudeCodeHarness(_cfg(anthropic_api_key=None, anthropic_model="")).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert result.model == "claude-sonnet-5-5"


def test_claude_run_raises_model_access_error(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _FakeSandbox(Path("/tmp/ws"))

    def run(command, *, env=None, timeout=0, cwd=None):
        sandbox.command = list(command)
        sandbox.env = dict(env or {})
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr="There's an issue with the selected model."
        )

    sandbox.run = run  # type: ignore[method-assign]
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    with pytest.raises(HarnessError) as caught:
        ClaudeCodeHarness(_cfg(anthropic_api_key=None, anthropic_model="")).run(
            sandbox, "task", [], timeout_sec=5
        )
    assert caught.value.exit_code == 2
    assert "its default model" in caught.value.message
    assert "--model" in (caught.value.hint or "")


def test_claude_run_model_access_error_names_requested_model(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    sandbox = _FakeSandbox(Path("/tmp/ws"))

    def run(command, *, env=None, timeout=0, cwd=None):
        sandbox.command = list(command)
        sandbox.env = dict(env or {})
        return subprocess.CompletedProcess(
            command, 1, stdout="", stderr="There's an issue with the selected model."
        )

    sandbox.run = run  # type: ignore[method-assign]
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    with pytest.raises(HarnessError) as caught:
        ClaudeCodeHarness(
            _cfg(anthropic_api_key=None, anthropic_model="claude-sonnet-4-20250514")
        ).run(sandbox, "task", [], timeout_sec=5)
    assert caught.value.exit_code == 2
    assert "claude-sonnet-4-20250514" in caught.value.message


def test_codex_run_reuses_host_login_without_copying_auth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_home = tmp_path / "home"
    real_codex = user_home / ".codex"
    foreign = real_codex / "skills" / "other-skill"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text(
        "---\nname: other-skill\ndescription: not this test\n---\nsecret-other\n",
        encoding="utf-8",
    )
    marker = "sg-test-auth-marker-not-a-secret"
    real_auth = real_codex / "auth.json"
    real_auth.write_text(f'{{"marker":"{marker}"}}\n', encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir()
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    result = CodexCliHarness(_cfg(codex_api_key=None)).run(sandbox, "task", [], timeout_sec=5)
    assert "CODEX_HOME" not in sandbox.env
    assert not (sandbox.workspace / ".skillgate" / "codex-home").exists()
    assert real_auth.read_text(encoding="utf-8") == f'{{"marker":"{marker}"}}\n'
    assert "CODEX_API_KEY" not in sandbox.env
    blob = json.dumps({"env": sandbox.env, "argv": sandbox.command})
    assert marker not in blob
    assert "secret-other" not in blob
    overrides = [sandbox.command[i + 1] for i, arg in enumerate(sandbox.command) if arg == "-c"]
    assert "skills.include_instructions=false" in overrides
    assert "skills.bundled.enabled=false" in overrides
    disabled = next(item for item in overrides if item.startswith("skills.config="))
    assert str(foreign / "SKILL.md") in disabled
    assert "enabled=false" in disabled
    assert "auth.json" not in disabled
    assert result.auth_mode == AUTH_CLI_LOGIN


def test_codex_key_does_not_replace_login_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    user_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir()
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    result = CodexCliHarness(_cfg(codex_api_key="k")).run(sandbox, "task", [], timeout_sec=5)
    assert "CODEX_HOME" not in sandbox.env
    assert not (sandbox.workspace / ".skillgate" / "codex-home").exists()
    assert sandbox.env["CODEX_API_KEY"] == "k"
    assert result.auth_mode == AUTH_API_KEY


def test_cursor_run_omits_empty_key_when_cli_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox = _FakeSandbox(tmp_path)
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._cursor_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    result = CursorAgentHarness(_cfg(cursor_api_key=None)).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert "CURSOR_API_KEY" not in sandbox.env
    assert result.auth_mode == AUTH_CLI_LOGIN


def test_harness_auth_status_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: None)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._codex_session_ok", lambda _c: False)
    monkeypatch.setattr("skillgate_ai.harness._claude_session_ok", lambda _c: False)
    rows = harness_auth_status(_cfg(anthropic_api_key="ant-test"))
    by_kind = {row["kind"]: row for row in rows}
    assert by_kind["cursor-agent"]["status"] == "logged in"
    assert by_kind["cursor-agent"]["installed"] is True
    assert by_kind["cursor-agent"]["auth"] == AUTH_CLI_LOGIN
    assert by_kind["codex"]["installed"] is False
    assert by_kind["codex"]["status"] == "none"
    assert "npm install -g @openai/codex" in by_kind["codex"]["install"]
    assert by_kind["claude"]["status"] == "API key"
    assert by_kind["claude"]["name"] == "Claude Code"
    blob = json.dumps(rows)
    assert "sk-" not in blob
    assert "ant-test" not in blob


def test_doctor_and_login_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "skillgate_ai.harness.harness_auth_status",
        lambda _cfg: [
            {
                "name": "Cursor",
                "kind": "cursor-agent",
                "agent": "cursor",
                "installed": True,
                "auth": "cli_login",
                "status": "logged in",
                "install": "curl https://cursor.com/install -fsS | bash",
                "command": "skillgate login cursor",
            },
            {
                "name": "Codex",
                "kind": "codex",
                "agent": "codex",
                "installed": True,
                "auth": "none",
                "status": "installed",
                "install": "npm install -g @openai/codex",
                "command": "skillgate login codex",
            },
            {
                "name": "Claude Code",
                "kind": "claude",
                "agent": "claude",
                "installed": False,
                "auth": "none",
                "status": "none",
                "install": "npm install -g @anthropic-ai/claude-code",
                "command": "skillgate login claude",
            },
        ],
    )
    runner = CliRunner()
    for args in (["doctor"], ["login", "--status"]):
        result = runner.invoke(app, args)
        out = plain_text(result.stdout + result.stderr)
        assert result.exit_code == 0, out
        assert "Cursor" in out
        assert "logged in" in out
        assert "Codex" in out
        assert "installed" in out
        assert "Claude Code" in out
        assert "npm install -g @anthropic-ai/claude-code" in out
    machine = runner.invoke(app, ["login", "--status", "--json"])
    payload = json.loads(machine.stdout)
    assert payload["harnesses"][0]["auth"] == "cli_login"
    assert "token" not in json.dumps(payload).lower() or "logged" in json.dumps(payload)


def test_login_runs_official_cli(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    monkeypatch.setattr(
        "skillgate_ai.harness._run_inherited",
        lambda argv, timeout=None: seen.append(list(argv)) or 0,
    )
    monkeypatch.setattr("skillgate_ai.harness._probe_cursor_login_status", lambda _b: True)
    result = run_official_login("cursor", _cfg())
    assert seen == [["/bin/agent", "login"]]
    assert result["ok"] is True
    assert result["status"] == "logged in"
    assert "token" not in json.dumps(result).lower()


def test_login_claude_and_codex_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    monkeypatch.setattr(
        "skillgate_ai.harness._run_inherited",
        lambda argv, timeout=None: seen.append(list(argv)) or 0,
    )
    monkeypatch.setattr("skillgate_ai.harness._probe_claude_login_status", lambda _b: True)
    monkeypatch.setattr("skillgate_ai.harness._probe_codex_login_status", lambda _b: True)
    assert run_official_login("claude", _cfg())["ok"] is True
    assert run_official_login("codex", _cfg())["ok"] is True
    assert seen == [["/bin/claude", "auth", "login"], ["/bin/codex", "login"]]


def test_login_missing_cli_returns_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: None)
    result = run_official_login("claude", _cfg())
    assert result["ok"] is False
    assert result["installed"] is False
    assert result["install"] == "npm install -g @anthropic-ai/claude-code"
    runner = CliRunner()
    cli = runner.invoke(app, ["login", "claude"])
    out = plain_text(cli.stdout + cli.stderr)
    assert cli.exit_code == 2, out
    assert "npm install -g @anthropic-ai/claude-code" in out


def test_login_claude_short_circuits_when_signed_in(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    called: list[str] = []

    def fake_login(agent: str, cfg) -> dict:
        called.append(agent)
        return {
            "ok": True,
            "agent": agent,
            "installed": True,
            "status": "logged in",
            "install": "",
            "command": f"skillgate login {agent}",
        }

    monkeypatch.setattr("skillgate_ai.harness.claude_auth_kind", lambda _c: AUTH_CLI_LOGIN)
    monkeypatch.setattr("skillgate_ai.harness.run_official_login", fake_login)
    runner = CliRunner()
    result = runner.invoke(app, ["login", "claude"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert out.strip() == "Claude Code is already signed in"
    assert called == []


def test_login_claude_force_runs_login(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []

    def fake_login(agent: str, cfg) -> dict:
        called.append(agent)
        return {
            "ok": True,
            "agent": agent,
            "installed": True,
            "status": "logged in",
            "install": "",
            "command": f"skillgate login {agent}",
        }

    monkeypatch.setattr("skillgate_ai.harness.claude_auth_kind", lambda _c: AUTH_CLI_LOGIN)
    monkeypatch.setattr("skillgate_ai.harness.run_official_login", fake_login)
    monkeypatch.setattr(
        "skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude"
    )
    monkeypatch.setattr("skillgate_ai.harness._probe_claude_login_status", lambda _b: True)
    monkeypatch.setattr("skillgate_ai.harness.harness_auth_status", lambda _c: [])
    runner = CliRunner()
    result = runner.invoke(app, ["login", "claude", "--force"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert called == ["claude"]
    assert "already signed in" not in out


def test_login_no_arg_runs_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.cli._stdin_is_tty", lambda: False)
    called: list[str] = []

    def fake_login(agent: str, cfg) -> dict:
        called.append(agent)
        return {
            "ok": True,
            "agent": agent,
            "installed": True,
            "status": "logged in",
            "install": "",
            "command": f"skillgate login {agent}",
        }

    monkeypatch.setattr(
        "skillgate_ai.harness.harness_auth_status",
        lambda _cfg: [
            {
                "name": "Cursor",
                "kind": "cursor-agent",
                "agent": "cursor",
                "installed": True,
                "auth": "none",
                "status": "installed",
                "install": "curl https://cursor.com/install -fsS | bash",
                "command": "skillgate login cursor",
            },
            {
                "name": "Codex",
                "kind": "codex",
                "agent": "codex",
                "installed": True,
                "auth": "api_key",
                "status": "API key",
                "install": "npm install -g @openai/codex",
                "command": "skillgate login codex",
            },
            {
                "name": "Claude Code",
                "kind": "claude",
                "agent": "claude",
                "installed": False,
                "auth": "none",
                "status": "none",
                "install": "npm install -g @anthropic-ai/claude-code",
                "command": "skillgate login claude",
            },
        ],
    )
    monkeypatch.setattr("skillgate_ai.harness.run_official_login", fake_login)
    runner = CliRunner()
    result = runner.invoke(app, ["login"])
    out = plain_text(result.stdout + result.stderr)
    assert result.exit_code == 0, out
    assert called == ["cursor"]


def test_missing_errors_mention_cli_login() -> None:
    claude = missing_key_error(for_claude=True)
    assert "skillgate login claude" in (claude.hint or "")
    assert "ANTHROPIC_API_KEY" in (claude.hint or "")
    generic = no_agent_available_error(_cfg())
    hint = generic.hint or ""
    assert "CURSOR_API_KEY" in hint
    assert "skillgate login" in hint


def test_combine_task_usage_labels_subscription() -> None:
    merged = combine_task_usage(
        {"tokens_total": 1000, "tokens_in": 800, "tokens_out": 200, "cost_usd": 1.25},
        {"usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": 0.03}},
        agent_model="claude-sonnet-4-20250514",
        agent_subscription=True,
    )
    assert merged is not None
    assert merged.get("agent_cost_usd") is None
    assert merged.get("agent_cost_label") == SUBSCRIPTION_COST_LABEL
    assert merged.get("judge_cost_usd") == 0.03
    assert merged.get("cost_usd") == 0.03
    assert merged.get("tokens_total") == 1120
    assert merged.get("cost_unknown") is not True


def test_cursor_status_accepts_authenticated_without_logged_in_word() -> None:
    assert _cursor_login_status_authenticated(0, "Authenticated\nAccount: you\n", "")
    assert _cursor_login_status_authenticated(0, "Account: you@example.com\n", "")
    assert not _cursor_login_status_authenticated(0, "Not authenticated\n", "")
    assert not _cursor_login_status_authenticated(1, "", "error")


def test_resolve_agent_bin_finds_user_local(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path / "home"
    dest = home / ".local" / "bin"
    dest.mkdir(parents=True)
    agent = dest / "agent"
    agent.write_text("#!/bin/sh\n", encoding="utf-8")
    agent.chmod(0o755)
    monkeypatch.setattr("skillgate_ai.harness.shutil.which", lambda _name: None)
    monkeypatch.setattr("skillgate_ai.harness.Path.home", lambda: home)
    assert _resolve_agent_bin("agent") == str(agent)
    assert _resolve_agent_bin("cursor-agent") == str(agent)


def test_cursor_exec_is_official_headless() -> None:
    cmd = _cursor_exec_command("/home/me/.local/bin/agent", "/tmp/ws", "do the task")
    assert cmd[0].endswith("agent")
    assert "-p" in cmd
    assert "--force" in cmd
    assert "--output-format" in cmd
    fmt = cmd[cmd.index("--output-format") + 1]
    assert fmt in {"json", "stream-json"}
    assert "--api-key" not in cmd


def test_cursor_cli_login_runs_without_api_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox = _FakeSandbox(tmp_path)
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    cfg = _cfg(cursor_api_key=None)
    assert has_startable_agent(cfg)
    harness = live_harness_or_error("cursor-agent", cfg)
    result = harness.run(sandbox, "task", [], timeout_sec=5)
    assert "-p" in sandbox.command
    assert "--force" in sandbox.command
    assert "CURSOR_API_KEY" not in sandbox.env
    assert "HOME" not in sandbox.env
    assert result.auth_mode == AUTH_CLI_LOGIN


def test_run_inherited_passes_no_open_browser(monkeypatch: pytest.MonkeyPatch) -> None:
    recorded: dict[str, object] = {}

    class FakePopen:
        def __init__(self, argv, start_new_session=False, **kwargs):
            recorded["argv"] = list(argv)
            recorded["start_new_session"] = start_new_session
            recorded["env"] = kwargs.get("env")
            self.returncode = 0

        def wait(self, timeout=None):
            del timeout
            return 0

        def poll(self):
            return 0

    monkeypatch.setattr("skillgate_ai.harness.subprocess.Popen", FakePopen)
    monkeypatch.setenv("NO_OPEN_BROWSER", "1")
    assert _run_inherited(["/bin/agent", "login"]) == 0
    assert recorded["argv"] == ["/bin/agent", "login"]
    assert recorded["start_new_session"] is True


def test_run_inherited_kills_process_group_on_timeout(tmp_path: Path) -> None:
    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text(
        "import signal, sys, time\n"
        "def on_term(signum, frame):\n"
        "    open(sys.argv[1], 'w').write('dead')\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, on_term)\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import os, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, sys.argv[2], sys.argv[3]])\n"
        "open(sys.argv[1], 'w').write(f'{os.getpid()} {child.pid}')\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    pids_file = tmp_path / "pids.txt"
    dead_marker = tmp_path / "dead.txt"
    code = _run_inherited(
        [sys.executable, str(parent), str(pids_file), str(grandchild), str(dead_marker)],
        timeout=1,
    )
    assert code == 124
    parent_pid, child_pid = (int(part) for part in pids_file.read_text(encoding="utf-8").split())
    assert _pid_gone(parent_pid)
    deadline = time.time() + 5
    while time.time() < deadline and not dead_marker.is_file():
        time.sleep(0.05)
    assert dead_marker.is_file()
    assert dead_marker.read_text(encoding="utf-8") == "dead"
    assert _pid_gone(child_pid)


def test_run_inherited_keyboard_interrupt_kills_group(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from skillgate_ai import harness

    grandchild = tmp_path / "grandchild.py"
    grandchild.write_text(
        "import signal, sys, time\n"
        "def on_term(signum, frame):\n"
        "    open(sys.argv[1], 'w').write('dead')\n"
        "    sys.exit(0)\n"
        "signal.signal(signal.SIGTERM, on_term)\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    parent = tmp_path / "parent.py"
    parent.write_text(
        "import os, subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, sys.argv[2], sys.argv[3]])\n"
        "open(sys.argv[1], 'w').write(f'{os.getpid()} {child.pid}')\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    pids_file = tmp_path / "pids.txt"
    dead_marker = tmp_path / "dead.txt"
    real_popen = harness.subprocess.Popen

    class KeyboardInterruptPopen:
        def __init__(self, argv, start_new_session=False):
            self._proc = real_popen(argv, start_new_session=start_new_session)
            self.start_new_session = start_new_session
            self._interrupted = False

        @property
        def pid(self):
            return self._proc.pid

        def wait(self, timeout=None):
            if not self._interrupted:
                self._interrupted = True
                deadline = time.time() + 5
                while time.time() < deadline and not pids_file.is_file():
                    time.sleep(0.05)
                raise KeyboardInterrupt()
            return self._proc.wait(timeout=timeout)

        def poll(self):
            return self._proc.poll()

    monkeypatch.setattr("skillgate_ai.harness.subprocess.Popen", KeyboardInterruptPopen)
    with pytest.raises(KeyboardInterrupt):
        harness._run_inherited(
            [sys.executable, str(parent), str(pids_file), str(grandchild), str(dead_marker)]
        )
    parent_pid, child_pid = (int(part) for part in pids_file.read_text(encoding="utf-8").split())
    assert _pid_gone(parent_pid)
    deadline = time.time() + 5
    while time.time() < deadline and not dead_marker.is_file():
        time.sleep(0.05)
    assert dead_marker.is_file()
    assert _pid_gone(child_pid)


def test_run_inherited_works_off_main_thread() -> None:
    errors: list[Exception] = []

    def call() -> None:
        try:
            code = _run_inherited([sys.executable, "-c", "pass"], timeout=30)
            assert code == 0
        except Exception as exc:  # pragma: no cover - transport for the assertion  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=call)
    thread.start()
    thread.join(timeout=30)
    assert not thread.is_alive()
    assert errors == []


def test_login_timeout_sec_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SKILLGATE_LOGIN_TIMEOUT", raising=False)
    assert _login_timeout_sec() == 600
    monkeypatch.setenv("SKILLGATE_LOGIN_TIMEOUT", "30")
    assert _login_timeout_sec() == 30
    monkeypatch.setenv("SKILLGATE_LOGIN_TIMEOUT", "not-a-number")
    assert _login_timeout_sec() == 600
    monkeypatch.setenv("SKILLGATE_LOGIN_TIMEOUT", "0")
    assert _login_timeout_sec() == 600


def test_codex_cli_login_defaults_to_chatgpt_luna() -> None:
    assert _codex_model_flag(None, cli_login=True) == "gpt-5.6-luna"
    assert _codex_model_flag("", cli_login=True) == "gpt-5.6-luna"
    assert _codex_model_flag("codex-default", cli_login=True) == "gpt-5.6-luna"
    assert _codex_model_flag("openai/gpt-4o-mini", cli_login=True) == "gpt-5.6-luna"
    assert _codex_model_flag("gpt-5.6-luna", cli_login=True) == "gpt-5.6-luna"
    cmd = _codex_exec_command(
        "/bin/codex",
        "/tmp/ws",
        "task",
        model=_codex_model_flag(None, cli_login=True),
    )
    assert cmd[cmd.index("-m") + 1] == "gpt-5.6-luna"


def test_codex_rejected_hint_names_config_and_excludes_rejected() -> None:
    blob = (
        "The 'gpt-5.6-sol' model is not supported when using Codex "
        "with a ChatGPT account. Supported models: gpt-5.6-luna, gpt-5.6-terra"
    )
    rejected, accepted = _codex_rejected_model("", blob)
    assert rejected == "gpt-5.6-sol"
    assert accepted == ["gpt-5.6-luna", "gpt-5.6-terra"]
    hint = codex_chatgpt_model_hint(rejected, accepted=accepted)
    assert "gpt-5.6-sol" not in hint
    assert "gpt-5.6-luna" in hint
    assert "~/.codex/config.toml" in hint


def test_codex_rejected_live_error_without_supported_list() -> None:
    blob = (
        "The 'gpt-5.6-sol' model is not supported when using Codex "
        "with a ChatGPT account."
    )
    rejected, accepted = _codex_rejected_model("", blob)
    assert rejected == "gpt-5.6-sol"
    assert accepted == []
    hint = codex_chatgpt_model_hint(rejected, accepted=accepted)
    assert "gpt-5.6-sol" not in hint
    assert "~/.codex/config.toml" in hint
    assert "gpt-5.6-luna" in hint


def test_codex_cli_login_run_passes_luna_when_no_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir()
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    result = CodexCliHarness(_cfg(codex_api_key=None, codex_model=None)).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert sandbox.command[sandbox.command.index("-m") + 1] == "gpt-5.6-luna"
    assert "CODEX_HOME" not in sandbox.env
    assert "CODEX_API_KEY" not in sandbox.env
    assert result.model == "gpt-5.6-luna"


def test_codex_run_reports_model_from_json_output() -> None:
    assert _codex_used_model("", None) is None
    assert _codex_used_model('{"type":"turn.completed"}', "gpt-5.6-luna") == "gpt-5.6-luna"
    assert (
        _codex_used_model(
            '{"type":"thread.started"}\n{"type":"x","model":"gpt-6-astra"}',
            "gpt-5.6-luna",
        )
        == "gpt-6-astra"
    )


def test_codex_run_names_rejected_model_from_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir()

    def reject(command, *, env=None, timeout=0, cwd=None):
        sandbox.command = list(command)
        sandbox.env = dict(env or {})
        return subprocess.CompletedProcess(
            command,
            1,
            stdout="",
            stderr=(
                "The 'gpt-5.6-sol' model is not supported when using Codex "
                "with a ChatGPT account."
            ),
        )

    sandbox.run = reject  # type: ignore[method-assign]
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    with pytest.raises(HarnessError) as caught:
        CodexCliHarness(_cfg(codex_api_key=None, codex_model="gpt-5.6-sol")).run(
            sandbox, "task", [], timeout_sec=5
        )
    assert "gpt-5.6-sol" in caught.value.message
    hint = caught.value.hint or ""
    assert "gpt-5.6-sol" not in hint
    assert "~/.codex/config.toml" in hint


def test_codex_exec_skillgate_argv(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Login stays on the ambient Codex home. Skill Gate does not read auth.json."""
    user_home = tmp_path / "home"
    real_codex = user_home / ".codex"
    real_codex.mkdir(parents=True)
    real_auth = real_codex / "auth.json"
    real_auth.write_text('{"marker":"sg-test-auth-marker-not-a-secret"}\n', encoding="utf-8")
    config = real_codex / "config.toml"
    original = b'model = "gpt-5.6-luna"\n'
    config.write_bytes(original)
    fake_bin = tmp_path / "codex"
    fake_bin.write_text(
        "#!/usr/bin/env python3\n"
        "print('{\"type\":\"turn.completed\"}')\n",
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir()

    def exec_run(command, *, env=None, timeout=0, cwd=None):
        sandbox.command = list(command)
        sandbox.env = dict(env or {})
        merged = {**os.environ, **sandbox.env}
        return subprocess.run(
            command,
            env=merged,
            cwd=str(cwd or sandbox.workspace),
            capture_output=True,
            text=True,
            timeout=timeout or 15,
            check=False,
        )

    sandbox.run = exec_run  # type: ignore[method-assign]
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: str(fake_bin))
    CodexCliHarness(_cfg(codex_api_key=None)).run(sandbox, "task", [], timeout_sec=5)
    assert "CODEX_HOME" not in sandbox.env
    assert "CODEX_API_KEY" not in sandbox.env
    assert config.read_bytes() == original
    assert real_auth.read_text(encoding="utf-8") == (
        '{"marker":"sg-test-auth-marker-not-a-secret"}\n'
    )
    blob = " ".join(sandbox.command)
    assert "sg-test-auth-marker-not-a-secret" not in blob
    assert "auth.json" not in blob
    overrides = [sandbox.command[i + 1] for i, arg in enumerate(sandbox.command) if arg == "-c"]
    assert "skills.include_instructions=false" in overrides


def test_check_no_judge_uses_cursor_cli_login(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import shutil

    from skillgate_ai.demo_files import ensure_demo_pdfs
    from skillgate_ai.engine import SuiteReport, TaskReport
    from skillgate_ai.gate import run_check
    from skillgate_ai.scorers import Score

    pack = tmp_path / "pdf"
    shutil.copytree(Path(__file__).resolve().parents[1] / "skills" / "pdf", pack)
    ensure_demo_pdfs(pack / "evals" / "fixtures")
    monkeypatch.setattr("skillgate_ai.harness._cursor_session_ok", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_agent_bin", lambda _p: "/bin/agent")
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("CURSOR_AGENT_BIN", "/bin/agent")

    def fake_eval(*_args, **_kwargs):
        return SuiteReport(
            suite="cases",
            title="pdf",
            skill="pdf",
            harness="cursor-agent",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="c1",
                    prompt="do it",
                    expect_skill="pdf",
                    passed=True,
                    scores=[Score(scorer="ok", passed=True, detail="ok")],
                    selected_skill="pdf",
                )
            ],
            skill_path=str(pack),
        )

    monkeypatch.setattr("skillgate_ai.gate.run_eval", fake_eval)
    result = run_check(
        pack,
        source="cli",
        root=tmp_path,
        no_judge=True,
        harness="cursor-agent",
    )
    assert result.exit_code != 2
    assert result.error is None or "No agent" not in (result.error.get("message") or "")
    assert result.report is not None


def test_run_official_login_times_out_returns_message(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")

    def fake_inherited(argv, *, timeout=None):
        seen["argv"] = list(argv)
        seen["timeout"] = timeout
        return 124

    monkeypatch.setattr("skillgate_ai.harness._run_inherited", fake_inherited)

    def no_probe(_b):
        raise AssertionError("probe must not run after a login timeout")

    monkeypatch.setattr("skillgate_ai.harness._probe_claude_login_status", no_probe)
    result = run_official_login("claude", _cfg())
    assert result["ok"] is False
    assert result["installed"] is True
    message = str(result["message"])
    assert "timed out" in message
    assert "skillgate login claude" in message
    assert seen["argv"] == ["/bin/claude", "auth", "login"]
    assert seen["timeout"] == 600


def test_run_official_login_timeout_env_is_honored(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, object] = {}
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setenv("SKILLGATE_LOGIN_TIMEOUT", "45")

    def fake_inherited(argv, *, timeout=None):
        seen["timeout"] = timeout
        return 124

    monkeypatch.setattr("skillgate_ai.harness._run_inherited", fake_inherited)
    monkeypatch.setattr("skillgate_ai.harness._probe_claude_login_status", lambda _b: True)
    run_official_login("claude", _cfg())
    assert seen["timeout"] == 45


def test_check_model_access_stops_after_first_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import shutil

    from skillgate_ai.demo_files import ensure_demo_pdfs
    from skillgate_ai.gate import run_check

    pack = tmp_path / "pdf"
    shutil.copytree(Path(__file__).resolve().parents[1] / "skills" / "pdf", pack)
    ensure_demo_pdfs(pack / "evals" / "fixtures")
    invocations = tmp_path / "claude-invocations.txt"
    fake_claude = tmp_path / "claude"
    fake_claude.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"pathlib.Path({str(invocations)!r}).open('a').write('x')\n"
        "sys.stderr.write(\"There's an issue with the selected model.\\n\")\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    fake_claude.chmod(0o755)
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: str(fake_claude))
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))

    result = run_check(pack, source="cli", root=tmp_path, harness="claude", no_judge=True)
    assert result.exit_code == 2, result.error
    assert result.error is not None
    message = str(result.error.get("message") or "")
    hint = str(result.error.get("hint") or "")
    assert "its default model" in message
    assert "--model sonnet" in hint
    assert "Fix the command or the script" not in message + hint
    assert "Paste this description into SKILL.md" not in message + hint
    assert invocations.read_text(encoding="utf-8") == "x"


def test_claude_model_persists_to_run_history_and_cli_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import shutil

    from skillgate_ai.demo_files import ensure_demo_pdfs
    from skillgate_ai.engine import SuiteReport, TaskReport
    from skillgate_ai.gate import run_check
    from skillgate_ai.history import load_history
    from skillgate_ai.report import format_cli
    from skillgate_ai.scorers import Score

    pack = tmp_path / "pdf"
    shutil.copytree(Path(__file__).resolve().parents[1] / "skills" / "pdf", pack)
    ensure_demo_pdfs(pack / "evals" / "fixtures")
    monkeypatch.setattr("skillgate_ai.harness._claude_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_claude_bin", lambda _p: "/bin/claude")
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))

    def fake_eval(*_args, **_kwargs):
        return SuiteReport(
            suite="cases",
            title="pdf",
            skill="pdf",
            harness="claude",
            sandbox="local",
            passed=True,
            tasks=[
                TaskReport(
                    task_id="c1",
                    prompt="do it",
                    expect_skill="pdf",
                    passed=True,
                    scores=[Score(scorer="ok", passed=True, detail="ok")],
                    selected_skill="pdf",
                    model="claude-opus-5-5",
                )
            ],
            skill_path=str(pack),
        )

    monkeypatch.setattr("skillgate_ai.gate.run_eval", fake_eval)
    result = run_check(pack, source="cli", root=tmp_path, harness="claude", no_judge=True)
    assert result.exit_code == 0, result.error
    assert result.report is not None
    config = result.report.config if isinstance(result.report.config, dict) else {}
    assert config["model"] == "claude-opus-5-5"
    rows = load_history(pack, limit=1)
    assert rows, "expected a persisted run history row"
    assert rows[-1]["config"]["model"] == "claude-opus-5-5"
    assert "Opus" in format_cli(result.report)
