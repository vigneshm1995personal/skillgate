"""Sanitized harness auth-failure diagnostics (no secret values)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from skillgate_ai.config import LLMConfig
from skillgate_ai.redact import redact_harness_text, tail_text

ENV_PRESENCE_KEYS: tuple[str, ...] = (
    "HOME",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
    "CURSOR_API_KEY",
    "CURSOR_AUTH_TOKEN",
    "CURSOR_SESSION",
    "DBUS_SESSION_BUS_ADDRESS",
    "CODEX_HOME",
    "CLAUDE_CONFIG_DIR",
)

_SECRET_FLAG_ARGS = frozenset({"--api-key", "-H", "--header"})


def env_presence_flags(env: dict[str, str]) -> dict[str, bool]:
    return {key: bool((env.get(key) or "").strip()) for key in ENV_PRESENCE_KEYS}


def auth_status_label(ok: bool | None) -> str:
    if ok is True:
        return "logged_in"
    if ok is False:
        return "not_logged_in"
    return "unknown"


def command_summary(argv: list[str], *, prompt: str | None = None) -> list[str]:
    """Executable + flags only; never include prompt bodies or secret flag values."""
    if not argv:
        return []
    out: list[str] = []
    skip_next = False
    for index, part in enumerate(argv):
        if skip_next:
            out.append("***")
            skip_next = False
            continue
        low = part.lower()
        if low in _SECRET_FLAG_ARGS:
            out.append(part)
            skip_next = True
            continue
        if prompt and index == len(argv) - 1 and part == prompt:
            out.append("<prompt>")
            continue
        if index == len(argv) - 1 and len(part) > 160:
            out.append("<prompt>")
            continue
        out.append(redact_harness_text(part))
    return out


@dataclass
class AuthFailureCapture:
    harness: str
    returncode: int | None
    command: list[str]
    child_env: dict[str, str]
    prompt: str
    stdout: str = ""
    stderr: str = ""
    transcript: str = ""
    auth_before: bool | None = None
    cursor_binary: str | None = None
    cfg: LLMConfig | None = None
    known_secret: str | None = None


def build_auth_diagnostics(capture: AuthFailureCapture) -> dict[str, Any]:
    stderr_src = capture.stderr or ""
    stdout_src = capture.stdout or ""
    known = capture.known_secret
    if not stderr_src.strip() and stdout_src.strip():
        stderr_tail = ""
        stdout_tail = tail_text(stdout_src, known=known)
    else:
        stderr_tail = tail_text(stderr_src, known=known)
        stdout_tail = tail_text(stdout_src, known=known)

    diag: dict[str, Any] = {
        "kind": "auth_failure",
        "harness": capture.harness,
        "exit_code": capture.returncode,
        "command_summary": command_summary(capture.command, prompt=capture.prompt),
        "stderr_tail": stderr_tail,
        "stdout_tail": stdout_tail,
        "env_presence": env_presence_flags(capture.child_env),
    }
    return _attach_cursor_auth_flip(diag, capture)


def _attach_cursor_auth_flip(diag: dict[str, Any], capture: AuthFailureCapture) -> dict[str, Any]:
    if capture.harness != "cursor-agent":
        return diag
    before = auth_status_label(capture.auth_before)
    diag["auth_status_before"] = before
    try:
        after_runner, after_host = _cursor_post_auth(capture)
    except Exception:  # noqa: BLE001 — probe failure must not break diagnostics
        diag["auth_status_after_runner_env"] = "error"
        diag["auth_status_after_host_env"] = "error"
        diag["diagnostics_error"] = True
        diag["auth_flipped"] = False
        return diag
    diag["auth_status_after_runner_env"] = auth_status_label(after_runner)
    diag["auth_status_after_host_env"] = auth_status_label(after_host)
    diag["auth_flipped"] = capture.auth_before is True and after_host is False
    return diag


def _cursor_post_auth(capture: AuthFailureCapture) -> tuple[bool | None, bool | None]:
    binary = capture.cursor_binary
    if not binary:
        return None, None
    from skillgate_ai.harness.auth import _probe_cursor_login_status

    runner: bool | None = None
    if capture.cfg is not None:
        from skillgate_ai.harness.cursor_env import cursor_runner_child_env

        runner = _probe_cursor_login_status(
            binary, env=cursor_runner_child_env(capture.cfg, task=capture.prompt)
        )
    host = _probe_cursor_login_status(binary, env=None)
    return runner, host
