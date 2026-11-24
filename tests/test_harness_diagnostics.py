from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from test_judge import _cfg

from skillgate_ai.errors import HarnessError
from skillgate_ai.harness.agents import CursorAgentHarness
from skillgate_ai.harness.cursor_env import cursor_runner_child_env
from skillgate_ai.harness.diagnostics import (
    AuthFailureCapture,
    build_auth_diagnostics,
    command_summary,
    env_presence_flags,
)
from skillgate_ai.harness.messages import _raise_if_auth_failed
from skillgate_ai.sandbox import _sandbox_env


def test_env_presence_flags_are_booleans_only() -> None:
    env = _sandbox_env({"CURSOR_API_KEY": "secret-not-in-flags"})
    flags = env_presence_flags(env)
    assert all(isinstance(value, bool) for value in flags.values())
    assert flags["CURSOR_API_KEY"] is True
    assert "secret" not in str(flags)


def test_command_summary_hides_prompt_and_api_key() -> None:
    prompt = "do the thing " + ("x" * 200)
    summary = command_summary(
        ["/bin/agent", "-p", "--api-key", "crsr_deadbeef", prompt],
        prompt=prompt,
    )
    assert "<prompt>" in summary
    assert "crsr_deadbeef" not in summary
    assert summary[3] == "***"


def test_build_auth_diagnostics_redacts_stderr() -> None:
    secret = "sk-testsecretvalue123456789012345678901"
    capture = AuthFailureCapture(
        harness="cursor-agent",
        returncode=2,
        command=["/bin/agent", "-p", "hello"],
        child_env=_sandbox_env(None),
        prompt="hello",
        stderr=f"not logged in; key={secret}",
        known_secret=secret,
    )
    diag = build_auth_diagnostics(capture)
    assert secret not in str(diag)
    assert diag["exit_code"] == 2
    assert "not logged in" in diag["stderr_tail"]


def test_raise_if_auth_failed_attaches_diagnostics() -> None:
    capture = AuthFailureCapture(
        harness="codex",
        returncode=1,
        command=["codex", "exec"],
        child_env=_sandbox_env(None),
        prompt="task",
    )
    with pytest.raises(HarnessError) as caught:
        _raise_if_auth_failed("", "not logged in", capture=capture)
    assert caught.value.diagnostics is not None
    assert caught.value.diagnostics["kind"] == "auth_failure"


def test_cursor_auth_flip_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[bool | None] = []

    def fake_probe(_binary: str, *, env=None) -> bool:
        if env is None:
            calls.append(False)
            return False
        calls.append(True)
        return True

    monkeypatch.setattr("skillgate_ai.harness.auth._probe_cursor_login_status", fake_probe)
    capture = AuthFailureCapture(
        harness="cursor-agent",
        returncode=2,
        command=["/bin/agent"],
        child_env=_sandbox_env(None),
        prompt="p",
        stderr="not logged in",
        auth_before=True,
        cursor_binary="/bin/agent",
        cfg=_cfg(cursor_api_key=None),
    )
    diag = build_auth_diagnostics(capture)
    assert diag["auth_flipped"] is True
    assert diag["auth_status_before"] == "logged_in"
    assert diag["auth_status_after_host_env"] == "not_logged_in"


class _FakeSandbox:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace

    def run(self, command, *, env=None, timeout=0, cwd=None):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="not logged in")


def test_cursor_run_passes_xdg_in_child_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setattr("skillgate_ai.harness.auth._cursor_ready", lambda _c: True)
    monkeypatch.setattr(
        "skillgate_ai.harness.auth._probe_cursor_login_status",
        lambda *a, **k: True,
    )
    monkeypatch.setattr("skillgate_ai.harness.bins._resolve_agent_bin", lambda _p: "/bin/agent")
    monkeypatch.setattr("skillgate_ai.harness.selection._parse_selected", lambda *a: "pdf")
    monkeypatch.setattr("skillgate_ai.harness.selection._parse_read_paths", lambda _t: [])
    monkeypatch.setattr("skillgate_ai.harness.selection._write_selection", lambda *a: None)
    monkeypatch.setattr("skillgate_ai.harness.selection._read_selection", lambda _w: "pdf")
    sandbox = _FakeSandbox(tmp_path / "ws")
    sandbox.workspace.mkdir(parents=True)

    def run(command, *, env=None, timeout=0, cwd=None):
        assert env is not None
        assert env.get("XDG_CONFIG_HOME") == str(tmp_path / "xdg-config")
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="not logged in")

    sandbox.run = run  # type: ignore[method-assign]
    cfg = _cfg(cursor_api_key=None)
    with pytest.raises(HarnessError) as caught:
        CursorAgentHarness(cfg).run(sandbox, "task", [], timeout_sec=5)
    assert caught.value.diagnostics is not None
    assert caught.value.diagnostics["env_presence"]["XDG_CONFIG_HOME"] is True


def test_cursor_child_env_blocks_secret_cursor_vars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/tmp/bus")
    for name in (
        "CURSOR_AUTH_TOKEN",
        "CURSOR_ACCESS_TOKEN",
        "CURSOR_SESSION_TOKEN",
        "CURSOR_SECRET",
        "CURSOR_COOKIE",
    ):
        monkeypatch.setenv(name, f"leak-{name}")
    cfg = _cfg(cursor_api_key=None)
    env = cursor_runner_child_env(cfg, task="probe")
    for name in (
        "CURSOR_AUTH_TOKEN",
        "CURSOR_ACCESS_TOKEN",
        "CURSOR_SESSION_TOKEN",
        "CURSOR_SECRET",
        "CURSOR_COOKIE",
    ):
        assert name not in env
    assert env.get("XDG_CONFIG_HOME") == str(tmp_path / "xdg")
    assert env.get("DBUS_SESSION_BUS_ADDRESS") == "unix:path=/tmp/bus"


def test_cursor_session_ok_uses_runner_child_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from skillgate_ai.harness import auth as auth_mod
    from skillgate_ai.harness.cursor_env import cursor_runner_child_env

    seen: dict[str, object] = {}

    def fake_probe(_binary: str, *, env=None) -> bool:
        seen["env"] = env
        return True

    def real_session_ok(cfg):
        from skillgate_ai.harness import bins

        binary = bins._resolve_agent_bin(cfg.cursor_agent_bin)
        if binary is None:
            return False
        return auth_mod._probe_cursor_login_status(binary, env=cursor_runner_child_env(cfg))

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg-data"))
    monkeypatch.setenv("CURSOR_AUTH_TOKEN", "must-not-leak")
    monkeypatch.setattr("skillgate_ai.harness.auth._probe_cursor_login_status", fake_probe)
    monkeypatch.setattr("skillgate_ai.harness.bins._resolve_agent_bin", lambda _p: "/bin/agent")
    monkeypatch.setattr("skillgate_ai.harness.auth._cursor_session_ok", real_session_ok)
    cfg = _cfg(cursor_api_key=None)
    assert real_session_ok(cfg) is True
    child = seen.get("env")
    assert isinstance(child, dict)
    assert child.get("XDG_DATA_HOME") == str(tmp_path / "xdg-data")
    assert "CURSOR_AUTH_TOKEN" not in child


def test_raise_if_auth_failed_survives_diagnostics_probe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(_binary: str, *, env=None) -> bool:
        raise RuntimeError("probe blew up")

    monkeypatch.setattr("skillgate_ai.harness.auth._probe_cursor_login_status", boom)
    capture = AuthFailureCapture(
        harness="cursor-agent",
        returncode=2,
        command=["/bin/agent"],
        child_env=_sandbox_env(None),
        prompt="p",
        stderr="not logged in",
        auth_before=True,
        cursor_binary="/bin/agent",
        cfg=_cfg(cursor_api_key=None),
    )
    with pytest.raises(HarnessError) as caught:
        _raise_if_auth_failed("", "not logged in", capture=capture)
    assert "not signed in" in caught.value.message
    assert caught.value.diagnostics is not None
    assert caught.value.diagnostics.get("diagnostics_error") is True
