"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import json
import subprocess

import skillgate_ai.harness.bins as bins
from skillgate_ai.config import (
    LLMConfig,
    agent_label,
)
from skillgate_ai.harness.base import _AGENT_INSTALL, AUTH_API_KEY, AUTH_CLI_LOGIN, AUTH_NONE


def _codex_auth_key(cfg: LLMConfig) -> str | None:
    return cfg.codex_api_key


_CODEX_LOGIN_STATUS_TIMEOUT_SEC = 5


def _codex_ready(cfg: LLMConfig) -> bool:
    """Explicit Codex may use an env key or a ChatGPT CLI session.

    Auto must not call this for has_any_key.
    """
    return bool(_codex_auth_key(cfg) or _codex_session_ok(cfg))


def _codex_login_status_authenticated(returncode: int, stdout: str, stderr: str) -> bool:
    if returncode != 0:
        return False
    text = f"{stdout}\n{stderr}".lower()
    if "not logged in" in text:
        return False
    return "logged in" in text


def _probe_codex_login_status(binary: str) -> bool:
    """Host `codex login status` only. Never read auth files."""
    try:
        proc = subprocess.run(  # noqa: S603 - binary resolved via harness.bins; fixed status subcommand
            [binary, "login", "status"],
            capture_output=True,
            text=True,
            timeout=_CODEX_LOGIN_STATUS_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return _codex_login_status_authenticated(proc.returncode, proc.stdout or "", proc.stderr or "")


def _codex_session_ok(cfg: LLMConfig) -> bool:
    binary = bins._resolve_codex_bin(cfg.codex_bin)
    if binary is None:
        return False
    return _probe_codex_login_status(binary)


_CURSOR_LOGIN_STATUS_TIMEOUT_SEC = 5


def _cursor_login_status_authenticated(returncode: int, stdout: str, stderr: str) -> bool:
    if returncode != 0:
        return False
    text = f"{stdout}\n{stderr}".lower()
    if "unable to fetch user details" in text:
        return False
    if "not logged in" in text or "not authenticated" in text:
        return False
    if "logged in" in text or "authenticated" in text:
        return True
    return "account:" in text


def _probe_cursor_login_status(binary: str) -> bool:
    """Host `cursor-agent status` / `agent status` only. Never read auth files."""
    try:
        proc = subprocess.run(  # noqa: S603 - binary resolved via harness.bins; fixed status subcommand
            [binary, "status"],
            capture_output=True,
            text=True,
            timeout=_CURSOR_LOGIN_STATUS_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return _cursor_login_status_authenticated(proc.returncode, proc.stdout or "", proc.stderr or "")


def _cursor_session_ok(cfg: LLMConfig) -> bool:
    binary = bins._resolve_agent_bin(cfg.cursor_agent_bin)
    if binary is None:
        return False
    return _probe_cursor_login_status(binary)


def _cursor_ready(cfg: LLMConfig) -> bool:
    return cursor_auth_kind(cfg) != AUTH_NONE


_CLAUDE_LOGIN_STATUS_TIMEOUT_SEC = 5


def _claude_login_status_authenticated(returncode: int, stdout: str, stderr: str) -> bool:
    if returncode != 0:
        return False
    for blob in (stdout, stderr):
        raw = (blob or "").strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict) and "loggedIn" in payload:
            return payload.get("loggedIn") is True
    text = f"{stdout}\n{stderr}".lower()
    if "not logged in" in text or "not authenticated" in text:
        return False
    return "logged in" in text or "authenticated" in text


def _probe_claude_login_status(binary: str) -> bool:
    """Host `claude auth status` only. Never read auth files."""
    try:
        proc = subprocess.run(  # noqa: S603 - binary resolved via harness.bins; fixed status subcommand
            [binary, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=_CLAUDE_LOGIN_STATUS_TIMEOUT_SEC,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return _claude_login_status_authenticated(proc.returncode, proc.stdout or "", proc.stderr or "")


def _claude_session_ok(cfg: LLMConfig) -> bool:
    binary = bins._resolve_claude_bin(cfg.claude_bin)
    if binary is None:
        return False
    return _probe_claude_login_status(binary)


def _claude_ready(cfg: LLMConfig) -> bool:
    return claude_auth_kind(cfg) != AUTH_NONE


def cursor_auth_kind(cfg: LLMConfig) -> str:
    if (cfg.cursor_api_key or "").strip():
        return AUTH_API_KEY
    if _cursor_session_ok(cfg):
        return AUTH_CLI_LOGIN
    return AUTH_NONE


def codex_auth_kind(cfg: LLMConfig) -> str:
    if _codex_auth_key(cfg):
        return AUTH_API_KEY
    if _codex_session_ok(cfg):
        return AUTH_CLI_LOGIN
    return AUTH_NONE


def claude_auth_kind(cfg: LLMConfig) -> str:
    if (cfg.anthropic_api_key or "").strip():
        return AUTH_API_KEY
    if _claude_session_ok(cfg):
        return AUTH_CLI_LOGIN
    return AUTH_NONE


def _display_status(*, installed: bool, auth: str) -> str:
    if auth == AUTH_API_KEY:
        return "API key"
    if auth == AUTH_CLI_LOGIN:
        return "logged in"
    if installed:
        return "installed"
    return "none"


def normalize_login_agent(raw: str | None) -> str | None:
    name = (raw or "").strip().lower()
    if name in {"cursor", "cursor-agent", "agent"}:
        return "cursor"
    if name == "codex":
        return "codex"
    if name in {"claude", "claude-code"}:
        return "claude"
    return None


def harness_auth_status(cfg: LLMConfig) -> list[dict[str, str | bool]]:
    """Per-agent install + auth. Never includes secrets."""
    rows: list[tuple[str, str, str, str | None, str]] = [
        (
            agent_label("cursor-agent"),
            "cursor-agent",
            "cursor",
            bins._resolve_agent_bin(cfg.cursor_agent_bin),
            cursor_auth_kind(cfg),
        ),
        (
            agent_label("codex"),
            "codex",
            "codex",
            bins._resolve_codex_bin(cfg.codex_bin),
            codex_auth_kind(cfg),
        ),
        (
            agent_label("claude"),
            "claude",
            "claude",
            bins._resolve_claude_bin(cfg.claude_bin),
            claude_auth_kind(cfg),
        ),
    ]
    out: list[dict[str, str | bool]] = []
    for name, kind, agent, binary, auth in rows:
        installed = binary is not None
        out.append(
            {
                "name": name,
                "kind": kind,
                "agent": agent,
                "installed": installed,
                "auth": auth,
                "status": _display_status(installed=installed, auth=auth),
                "install": _AGENT_INSTALL[agent],
                "command": f"skillgate login {agent}",
            }
        )
    return out


def format_harness_status(rows: list[dict[str, str | bool]]) -> str:
    lines: list[str] = []
    for row in rows:
        lines.append(str(row["name"]))
        lines.append(f"  status     {row['status']}")
        if not row["installed"]:
            lines.append(f"  install    {row['install']}")
        elif row["auth"] == AUTH_NONE:
            lines.append(f"  login      {row['command']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
