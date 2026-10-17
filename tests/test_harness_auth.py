"""Auth resolution: API key vs CLI login vs none, for Cursor, Codex, and Claude Code."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from typer.testing import CliRunner

from conftest import plain_text
from skillgate_ai.cli import app
from skillgate_ai.config import missing_key_error, no_agent_available_error
from skillgate_ai.harness import (
    AUTH_API_KEY,
    AUTH_CLI_LOGIN,
    AUTH_NONE,
    ClaudeCodeHarness,
    CodexCliHarness,
    CursorAgentHarness,
    _claude_login_status_authenticated,
    _codex_login_status_authenticated,
    _cursor_login_status_authenticated,
    claude_auth_kind,
    codex_auth_kind,
    cursor_auth_kind,
    harness_auth_status,
    harness_is_startable,
    live_harness_or_error,
    run_official_login,
)
from skillgate_ai.usage import SUBSCRIPTION_COST_LABEL, combine_task_usage
from test_judge import _cfg


class _FakeSandbox:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.env: dict[str, str] = {}

    def run(self, command, *, env=None, timeout=0, cwd=None):
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


def test_codex_run_reuses_host_login_without_copying_auth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir()
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    result = CodexCliHarness(_cfg(codex_api_key=None)).run(sandbox, "task", [], timeout_sec=5)
    assert "CODEX_HOME" not in sandbox.env
    assert "CODEX_API_KEY" not in sandbox.env
    assert result.auth_mode == AUTH_CLI_LOGIN


def test_codex_run_isolates_home_when_key_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir()
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    result = CodexCliHarness(_cfg(codex_api_key="k")).run(sandbox, "task", [], timeout_sec=5)
    home = Path(sandbox.env["CODEX_HOME"])
    assert str(home).endswith("/.skillgate/codex-home")
    assert not (home / "auth.json").exists()
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
        lambda argv: seen.append(list(argv)) or 0,
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
        lambda argv: seen.append(list(argv)) or 0,
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
