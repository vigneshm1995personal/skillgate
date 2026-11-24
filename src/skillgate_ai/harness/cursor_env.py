"""Cursor harness child environment — match sandbox contract used by `cursor-agent -p`."""

from __future__ import annotations

import os

from skillgate_ai.config import LLMConfig
from skillgate_ai.sandbox import _sandbox_env

_CURSOR_PASSTHROUGH_EXACT = frozenset({"DBUS_SESSION_BUS_ADDRESS"})


def _cursor_passthrough_key(name: str) -> bool:
    if name.startswith("XDG_") or name in _CURSOR_PASSTHROUGH_EXACT:
        return True
    return name.startswith("CURSOR_") and name != "CURSOR_API_KEY"


def _cursor_harness_extra(cfg: LLMConfig) -> dict[str, str]:
    """Non-secret host paths Cursor CLI needs inside the sandbox allowlist filter."""
    extra: dict[str, str] = {}
    for key, value in os.environ.items():
        if not (value or "").strip():
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
