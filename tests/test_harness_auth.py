"""Auth resolution: API key vs CLI login vs none, for Cursor, Codex, and Claude Code."""

from __future__ import annotations

import json
import os
import subprocess
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
    _cursor_exec_command,
    _cursor_login_status_authenticated,
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
    user_home = tmp_path / "home"
    real_codex = user_home / ".codex"
    real_codex.mkdir(parents=True)
    marker = "sg-test-auth-marker-not-a-secret"
    real_auth = real_codex / "auth.json"
    real_auth.write_text(f'{{"marker":"{marker}"}}\n', encoding="utf-8")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir()
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    result = CodexCliHarness(_cfg(codex_api_key=None)).run(sandbox, "task", [], timeout_sec=5)
    home = Path(sandbox.env["CODEX_HOME"])
    assert str(home).endswith("/.skillgate/codex-home")
    linked = home / "auth.json"
    assert linked.is_symlink()
    assert linked.resolve() == real_auth.resolve()
    assert "CODEX_API_KEY" not in sandbox.env
    assert marker not in json.dumps(sandbox.env)
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

    def fake_run(argv, **kwargs):
        recorded["argv"] = list(argv)
        recorded["kwargs"] = kwargs
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr("skillgate_ai.harness.subprocess.run", fake_run)
    monkeypatch.setenv("NO_OPEN_BROWSER", "1")
    assert _run_inherited(["/bin/agent", "login"]) == 0
    env = recorded["kwargs"].get("env")
    assert env is None or env.get("NO_OPEN_BROWSER") == "1"
    assert recorded["argv"] == ["/bin/agent", "login"]


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
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir()
    _stub_run(monkeypatch)
    monkeypatch.setattr("skillgate_ai.harness._codex_ready", lambda _c: True)
    monkeypatch.setattr("skillgate_ai.harness._resolve_codex_bin", lambda _p: "/bin/codex")
    CodexCliHarness(_cfg(codex_api_key=None, codex_model=None)).run(
        sandbox, "task", [], timeout_sec=5
    )
    assert sandbox.command[sandbox.command.index("-m") + 1] == "gpt-5.6-luna"
    assert sandbox.env["CODEX_HOME"].endswith("/.skillgate/codex-home")


def test_codex_run_names_rejected_model_from_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
    """A Skill Gate Codex run must not mutate the user's ~/.codex/config.toml."""
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
        "import os, pathlib, sys\n"
        "home = pathlib.Path(os.environ.get('CODEX_HOME') or (pathlib.Path.home() / '.codex'))\n"
        "home.mkdir(parents=True, exist_ok=True)\n"
        "args = sys.argv[1:]\n"
        "cwd = args[args.index('-C') + 1] if '-C' in args else str(pathlib.Path.cwd())\n"
        "cfg = home / 'config.toml'\n"
        "prior = cfg.read_text() if cfg.exists() else ''\n"
        "cfg.write_text(prior + f'\\n[projects.\"{cwd}\"]\\ntrust_level = \"trusted\"\\n')\n"
        "print('{\"type\":\"turn.completed\"}')\n",
        encoding="utf-8",
    )
    fake_bin.chmod(0o755)
    monkeypatch.setenv("HOME", str(user_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: user_home))
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
    assert config.read_bytes() == original
    isolated = Path(sandbox.env["CODEX_HOME"]) / "config.toml"
    assert isolated.is_file()
    assert "trust_level" in isolated.read_text(encoding="utf-8")
    assert "sg-test-auth-marker-not-a-secret" not in (sandbox.env.get("CODEX_API_KEY") or "")


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
