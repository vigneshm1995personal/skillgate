"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import os
from collections.abc import Callable
import signal
import subprocess
import threading
from typing import Any

import skillgate_ai.harness.auth as auth
import skillgate_ai.harness.bins as bins
from skillgate_ai.config import (
    LLMConfig,
    agent_label,
)
from skillgate_ai.harness.base import _AGENT_INSTALL, _login_timeout_sec


def _terminate_process_group(proc: subprocess.Popen[Any]) -> None:
    """SIGTERM the child's process group, then SIGKILL if it ignores the term."""
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        try:  # noqa: SIM105
            os.kill(proc.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            pass
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:  # noqa: SIM105
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:  # noqa: SIM105
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def _run_inherited(argv: list[str], *, timeout: float | None = None) -> int:
    """Run an official login CLI with the user's terminal (OAuth / browser).

    The child runs in its own session/process group so Ctrl-C, SIGTERM, or a
    timeout can tear down the whole tree (no orphaned `claude auth login`).

    `signal.signal` raises ValueError outside the main thread, so the SIGTERM
    forwarder is only installed (and restored) from the main thread; the local
    UI can start a login from a worker thread.
    """
    proc = subprocess.Popen(argv, start_new_session=True)  # noqa: S603 - resolved official agent CLI + fixed login subcommand
    interrupted: dict[str, int | None] = {"sig": None}
    in_main_thread = threading.current_thread() is threading.main_thread()

    def _on_sigterm(signum: int, frame: object) -> None:
        del frame
        interrupted["sig"] = signum
        _terminate_process_group(proc)

    previous = signal.signal(signal.SIGTERM, _on_sigterm) if in_main_thread else None
    try:
        code: int | None
        try:
            code = int(proc.wait(timeout=timeout) or 0)
        except subprocess.TimeoutExpired:
            _terminate_process_group(proc)
            code = 124
        except KeyboardInterrupt:
            _terminate_process_group(proc)
            raise
        if interrupted["sig"] is not None:
            return 128 + int(interrupted["sig"])
        return code
    finally:
        if in_main_thread:
            signal.signal(signal.SIGTERM, previous)


def run_official_login(agent: str, cfg: LLMConfig) -> dict[str, str | bool]:
    """Start the agent's official login, then verify with a status probe."""
    kind = auth.normalize_login_agent(agent)
    if kind is None:
        return {
            "ok": False,
            "agent": (agent or "").strip() or "unknown",
            "installed": False,
            "status": "none",
            "install": "",
            "command": "skillgate login",
            "message": "Pass an agent id: cursor, claude, or codex.",
        }
    probe: Callable[..., bool]
    if kind == "cursor":
        binary = bins._resolve_agent_bin(cfg.cursor_agent_bin)
        argv = [binary, "login"] if binary else []
        probe = auth._probe_cursor_login_status
    elif kind == "codex":
        binary = bins._resolve_codex_bin(cfg.codex_bin)
        argv = [binary, "login"] if binary else []
        probe = auth._probe_codex_login_status
    else:
        binary = bins._resolve_claude_bin(cfg.claude_bin)
        argv = [binary, "auth", "login"] if binary else []
        probe = auth._probe_claude_login_status
    install = _AGENT_INSTALL[kind]
    command = f"skillgate login {kind}"
    if binary is None:
        return {
            "ok": False,
            "agent": kind,
            "installed": False,
            "status": "none",
            "install": install,
            "command": command,
            "message": "Not installed. Install this agent's CLI, then sign in.",
        }
    code = _run_inherited(argv, timeout=_login_timeout_sec())
    if code == 124:
        return {
            "ok": False,
            "agent": kind,
            "installed": True,
            "status": "installed",
            "install": install,
            "command": command,
            "message": f"{agent_label(kind)} login timed out. Run `{command}` in your terminal.",
        }
    logged_in = probe(binary)
    return {
        "ok": logged_in,
        "agent": kind,
        "installed": True,
        "status": "logged in" if logged_in else "installed",
        "install": install,
        "command": command,
        "message": (
            f"{agent_label(kind)} is logged in."
            if logged_in
            else f"{agent_label(kind)} login did not complete. Run `{command}` in your terminal."
        ),
    }
