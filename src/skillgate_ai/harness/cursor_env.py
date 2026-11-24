"""Cursor harness child environment — match sandbox contract used by `cursor-agent -p`."""

from __future__ import annotations

import os
import re

from skillgate_ai.config import LLMConfig
from skillgate_ai.sandbox import _sandbox_env

_SAFE_PASSTHROUGH_EXACT = frozenset(
    {
        "DBUS_SESSION_BUS_ADDRESS",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        "XDG_CACHE_HOME",
        "XDG_STATE_HOME",
        "XDG_RUNTIME_DIR",
    }
)

_SENSITIVE_NAME_RE = re.compile(
    r"(?:TOKEN|SECRET|COOKIE|PASSWORD|PASSWD|CREDENTIAL|AUTH|\bKEY\b)",
    re.IGNORECASE,
)


def _cursor_passthrough_key(name: str) -> bool:
    if name in _SAFE_PASSTHROUGH_EXACT:
        return True
    if name.startswith("XDG_"):
        return _SENSITIVE_NAME_RE.search(name) is None
    return False


def _cursor_harness_extra(cfg: LLMConfig) -> dict[str, str]:
    """Non-secret host paths Cursor CLI needs inside the sandbox allowlist filter."""
    extra: dict[str, str] = {}
    for key, value in os.environ.items():
        if not (value or "").strip():
            continue
        if _SENSITIVE_NAME_RE.search(key) and key != "CURSOR_API_KEY":
            continue
        if _cursor_passthrough_key(key):
            extra[key] = value
    api_key = (cfg.cursor_api_key or "").strip()
    if api_key:
        extra["CURSOR_API_KEY"] = api_key
    return extra


def cursor_runner_child_env(cfg: LLMConfig, *, task: str | None = None) -> dict[str, str]:
    """Full env dict for `cursor-agent status` probes that must match harness runs."""
    base = _cursor_harness_extra(cfg)
    if task is not None:
        base["SKILLGATE_TASK"] = task
    return _sandbox_env(base)
