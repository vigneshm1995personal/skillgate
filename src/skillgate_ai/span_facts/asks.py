from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from skillgate_ai.span_facts.patterns import (
    _ANSWER_NO_IF,
    _AT_MOST_ONCE,
    _FILE,
    _MORE_THAN_ONCE,
    _NO_DUPLICATE,
    _REPLY,
    _RETURN,
    _SNAKE,
    _STOP,
    _TOOL_CALLED,
    _TOOL_TICK,
)
from skillgate_ai.span_facts.tools import count_tool_calls


def log_fact_kind(ask: str) -> str | None:
    """Which log-fact shape this extra check is, or None if the judge must score it."""
    return _fact_kind(ask)


def _predicate(yes: bool, *, source: str, reason: str | None = None) -> dict[str, Any]:
    value = 1.0 if yes else 0.0
    out: dict[str, Any] = {"probability": value, "source": source}
    if reason:
        out["reason"] = reason
    return out


def _primary_tool(
    ask: str,
    spans: Sequence[Mapping[str, Any]] | None = None,
    *,
    trajectory: Mapping[str, Any] | None = None,
) -> str | None:
    candidates = _tool_candidates(ask)
    if not candidates:
        return None
    present = [
        name for name in candidates if count_tool_calls(spans, name, trajectory=trajectory) > 0
    ]
    if present:
        return present[0]
    snake = [name for name in candidates if "_" in name]
    if snake:
        return snake[0]
    return candidates[0]


def _tool_candidates(ask: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def add(token: str) -> None:
        name = token.strip().lower()
        if len(name) < 3 or name in _STOP or name in seen:
            return
        seen.add(name)
        names.append(name)

    for match in _TOOL_TICK.finditer(ask):
        add(match.group(1))
    for match in _SNAKE.finditer(ask):
        add(match.group(1))
    for match in _TOOL_CALLED.finditer(ask):
        add(match.group(1))
    return names


def _fact_kind(ask: str) -> str | None:
    if _MORE_THAN_ONCE.search(ask):
        return "count"
    if _REPLY.search(ask):
        return None
    if _RETURN.search(ask):
        return "return"
    if _TOOL_CALLED.search(ask) or re.search(
        r"\b(?:was|were)\s+.{0,20}called\b", ask, re.IGNORECASE
    ):
        return "called"
    return None


def _primary_file(ask: str) -> str | None:
    match = _FILE.search(ask or "")
    if not match:
        return None
    return (match.group(1) or match.group(2) or "").strip() or None


def _count_is_yes(ask: str, count: int) -> bool:
    """Yes/No polarity for a count fact. Never rewrite the ask."""
    text = ask or ""
    no_if_more = bool(
        _ANSWER_NO_IF.search(text) and re.search(r"more than once", text, re.IGNORECASE)
    )
    if no_if_more or _AT_MOST_ONCE.search(text) or _NO_DUPLICATE.search(text):
        return count <= 1
    if re.search(r"more than once", text, re.IGNORECASE):
        return count > 1
    return count <= 1
