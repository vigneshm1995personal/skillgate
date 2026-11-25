from __future__ import annotations

import json
from typing import Any, TypeVar

from skillgate_ai.usage.model import (
    _COST_KEYS,
    _IN_KEYS,
    _OUT_KEYS,
    _TOTAL_KEYS,
    Usage,
)

_Num = TypeVar("_Num", int, float)


def parse_usage_line(line: str) -> Usage | None:
    """Usage carried by a single stdout line, or None when it has none."""
    text = line.strip()
    if not text.startswith("{"):
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(obj, dict):
        return None
    return usage_from_event(obj)


def usage_from_event(obj: dict[str, Any]) -> Usage | None:
    for candidate in _usage_objects(obj):
        parsed = _usage_from_tokens(candidate)
        if parsed is not None:
            return parsed
    return None


def merge_usage(current: Usage, update: Usage) -> Usage:
    """Monotonic merge. Both Codex shapes report cumulative counters."""
    return Usage(
        tokens_in=_pick(current.tokens_in, update.tokens_in),
        tokens_out=_pick(current.tokens_out, update.tokens_out),
        tokens_total=_pick(current.tokens_total, update.tokens_total),
        cost_usd=_pick(current.cost_usd, update.cost_usd),
    )


def usage_from_mapping(raw: Any) -> Usage | None:
    if not isinstance(raw, dict):
        return None
    return _usage_from_tokens(raw)


def _pick(current: _Num | None, update: _Num | None) -> _Num | None:
    if update is None:
        return current
    if current is None:
        return update
    return max(current, update)


def _usage_objects(obj: dict[str, Any]):
    kind = obj.get("type")
    if kind in {"turn.completed", "result"}:
        # Codex exec turn, or Cursor / Claude Code stream-json final result.
        usage = obj.get("usage")
        merged: dict[str, Any] = dict(usage) if isinstance(usage, dict) else {}
        for key in _COST_KEYS:
            if key in obj:
                merged[key] = obj[key]
        if merged:
            yield merged
        return
    if kind == "event_msg":
        payload = obj.get("payload")
        if isinstance(payload, dict):
            if payload.get("type") == "token_count":
                info = payload.get("info")
                if isinstance(info, dict):
                    yield info.get("total_token_usage") or info.get("last_token_usage")
            yield payload.get("usage")
        return
    payload = obj.get("payload")
    if isinstance(payload, dict):
        # Session rollouts wrap token_usage_record fields under `payload`.
        yield payload.get("thread_token_usage")
        yield payload.get("turn_token_usage")
        yield payload.get("total_token_usage")
        yield payload.get("usage")
    yield obj.get("thread_token_usage")
    yield obj.get("turn_token_usage")
    yield obj.get("total_token_usage")
    yield obj.get("usage")
    yield obj


def _usage_from_tokens(raw: Any) -> Usage | None:
    if not isinstance(raw, dict):
        return None
    tokens_in = _number_field(raw, _IN_KEYS)
    tokens_out = _number_field(raw, _OUT_KEYS)
    tokens_total = _number_field(raw, _TOTAL_KEYS)
    cost = _number_field(raw, _COST_KEYS, as_float=True)
    if tokens_total is None and (tokens_in is not None or tokens_out is not None):
        tokens_total = (int(tokens_in) if tokens_in is not None else 0) + (
            int(tokens_out) if tokens_out is not None else 0
        )
    if tokens_in is None and tokens_out is None and tokens_total is None and cost is None:
        return None
    return Usage(
        tokens_in=None if tokens_in is None else int(tokens_in),
        tokens_out=None if tokens_out is None else int(tokens_out),
        tokens_total=None if tokens_total is None else int(tokens_total),
        cost_usd=cost,
    )


def _number_field(
    raw: dict[str, Any], keys: tuple[str, ...], *, as_float: bool = False
) -> float | None:
    for key in keys:
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(value, bool):
            continue
        number: float | None = None
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            try:
                number = float(value)
            except ValueError:
                continue
        if number is None:
            continue
        return number if as_float else float(int(number))
    return None
