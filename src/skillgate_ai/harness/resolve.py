"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import skillgate_ai.harness.auth as auth
import skillgate_ai.harness.bins as bins
from skillgate_ai.config import (
    LLMConfig,
    missing_key_error,
    no_agent_available_error,
)
from skillgate_ai.errors import HarnessError, MissingLLMKeyError
from skillgate_ai.harness.agents import ClaudeCodeHarness, CodexCliHarness, CursorAgentHarness
from skillgate_ai.harness.base import Harness


def harness_is_startable(harness: Harness, cfg: LLMConfig) -> bool:
    """True when this harness can spawn (CLI on PATH / key or CLI login)."""
    if isinstance(harness, CodexCliHarness):
        return auth._codex_ready(cfg) and bins._resolve_codex_bin(cfg.codex_bin) is not None
    if isinstance(harness, CursorAgentHarness):
        return auth._cursor_ready(cfg) and bins._resolve_agent_bin(cfg.cursor_agent_bin) is not None
    if isinstance(harness, ClaudeCodeHarness):
        return auth._claude_ready(cfg) and bins._resolve_claude_bin(cfg.claude_bin) is not None
    return True


def _named_harness(kind: str, cfg: LLMConfig) -> Harness:
    if kind in {"cursor-agent", "cursor", "agent"}:
        return CursorAgentHarness(cfg)
    if kind == "codex":
        return CodexCliHarness(cfg)
    if kind in {"claude", "claude-code"}:
        return ClaudeCodeHarness(cfg)
    if kind in {"llm", "byollm", "demo"}:
        raise HarnessError(
            f"The {kind!r} harness was removed.",
            hint="Use auto, cursor-agent, codex, or claude.",
            exit_code=2,
        )
    raise HarnessError(
        f"Unknown harness {kind!r}",
        hint="Use auto, cursor-agent, codex, or claude.",
    )


def resolve_harness(kind: str, cfg: LLMConfig) -> Harness:
    return live_harness_or_error(kind, cfg)


_LIVE_HARNESS_KINDS = frozenset(
    {
        "auto",
        "cursor-agent",
        "cursor",
        "agent",
        "codex",
        "claude",
        "claude-code",
    }
)

_AGENT_PRIORITY = ("cursor-agent", "codex", "claude")


def _agent_candidates(cfg: LLMConfig) -> list[tuple[str, Harness]]:
    found: list[tuple[str, Harness]] = []
    if auth._cursor_ready(cfg) and bins._resolve_agent_bin(cfg.cursor_agent_bin):
        found.append(("cursor-agent", CursorAgentHarness(cfg)))
    if auth._codex_ready(cfg) and bins._resolve_codex_bin(cfg.codex_bin):
        found.append(("codex", CodexCliHarness(cfg)))
    if auth._claude_ready(cfg) and bins._resolve_claude_bin(cfg.claude_bin):
        found.append(("claude", ClaudeCodeHarness(cfg)))
    order = {name: index for index, name in enumerate(_AGENT_PRIORITY)}
    found.sort(key=lambda item: order.get(item[0], 99))
    return found


def startable_agent_kinds(cfg: LLMConfig) -> list[str]:
    return [name for name, harness in _agent_candidates(cfg) if harness_is_startable(harness, cfg)]


def has_startable_agent(cfg: LLMConfig) -> bool:
    return bool(startable_agent_kinds(cfg))


def live_harness_or_error(kind: str, cfg: LLMConfig) -> Harness:
    """Pick a live harness. Missing agent → MissingLLMKeyError (exit 2)."""
    kind = (kind or "auto").lower()
    if kind in {"llm", "byollm", "demo"}:
        raise HarnessError(
            f"The {kind!r} harness was removed.",
            hint="Use auto, cursor-agent, codex, or claude.",
            exit_code=2,
        )
    if kind not in _LIVE_HARNESS_KINDS:
        return _named_harness(kind, cfg)
    if kind == "auto":
        agents = _agent_candidates(cfg)
        if not agents:
            raise no_agent_available_error(cfg)
        harness = agents[0][1]
        if not harness_is_startable(harness, cfg):
            raise no_agent_available_error(cfg)
        return harness
    harness = _named_harness(kind, cfg)
    if not harness_is_startable(harness, cfg):
        if kind in {"cursor-agent", "cursor", "agent"}:
            raise missing_key_error(for_cursor=True)
        if kind == "codex":
            raise missing_key_error(for_codex=True)
        if kind in {"claude", "claude-code"}:
            raise missing_key_error(for_claude=True)
        raise no_agent_available_error(cfg)
    return harness


def auto_live_harness_name(cfg: LLMConfig) -> str:
    """Harness Auto will run — picker catalog key."""
    try:
        return live_harness_or_error("auto", cfg).name
    except MissingLLMKeyError:
        return "auto"
