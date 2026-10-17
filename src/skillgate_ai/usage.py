"""Harness-neutral token and cost usage parsed from live harness output.

Every harness funnels its machine-readable usage through this module so the
Gate panel, run snapshots, and suite totals all read one `Usage` shape:
`tokens_in`, `tokens_out`, `tokens_total`, `cost_usd` (nullable). A harness
that reports tokens but no dollars leaves `cost_usd` null until
`estimate_usage_cost_usd` fills it from a known model price table.

Codex `exec --json` prints one JSON object per line. The event carrying real
token counts is `turn.completed`:

    {"type":"turn.completed","usage":{"input_tokens":18102,
     "cached_input_tokens":11136,"output_tokens":210,...}}

Cursor Agent `--output-format stream-json` prints one JSON event per line. The
final `result` event carries camelCase usage (no cost):

    {"type":"result","subtype":"success","is_error":false,"result":"pong",
     "usage":{"inputTokens":10146,"outputTokens":101,
              "cacheReadTokens":4736,"cacheWriteTokens":0}}

Anthropic messages and OpenAI-compatible chat completions carry `usage` in the
response JSON (`input_tokens`/`output_tokens` or
`prompt_tokens`/`completion_tokens`) — the same parser reads both.

`parse_usage_line` is deliberately permissive: along with those events it
understands the Codex session `event_msg`/`token_count` shape, the
`token_usage_record` shape, and any object whose `usage`/`total_token_usage`
carries a recognized token key. Lines without usage return None.

`render_stream_line` turns Codex and Cursor JSONL rows into short human lines
for the live tail and the selection transcript; it returns unrecognized input
unchanged.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# Order matters: prefer the harness's own underscore names, then OpenAI's
# prompt/completion names, then Cursor's camelCase, then short aliases.
_IN_KEYS = ("tokens_in", "input_tokens", "prompt_tokens", "inputTokens", "input")
_OUT_KEYS = ("tokens_out", "output_tokens", "completion_tokens", "outputTokens", "output")
_TOTAL_KEYS = ("tokens_total", "total_tokens", "totalTokens")
# USD per 1M tokens (input, output) for models Skill Gate commonly runs.
_MODEL_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.6-luna": (0.10, 0.50),
    "gpt-5.6-terra": (1.25, 10.00),
    "gpt-5.6-sol": (0.25, 2.00),
    "gpt-6-astra": (0.10, 0.50),
    "composer-2.5": (1.25, 10.00),
    "composer-2.5-fast": (0.50, 4.00),
    "codex-default": (1.25, 10.00),
    "claude-fable-5-1": (10.00, 50.00),
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
}

SUBSCRIPTION_COST_LABEL = "subscription (not metered)"

_COST_KEYS = (
    "cost_usd",
    "total_cost_usd",
    "total_usd",
    "costUsd",
    "totalCostUsd",
    "cost",
    "total_cost",
)

_CODEX_BOOKKEEPING = frozenset({"thread.started", "turn.started", "turn.completed"})
# Cursor stream-json envelopes that carry no human text for the live tail.
_CURSOR_BOOKKEEPING = frozenset({"system", "user", "result"})
# Claude / Cursor events that are account or transport noise, not evidence.
_NON_CONTENT_EVENTS = frozenset(
    {
        "rate_limit_event",
        "system",
        "ping",
        "stream_event",
        "hook_started",
        "hook_progress",
        "hook_response",
        "prompt_suggestion",
    }
)


@dataclass(frozen=True)
class Usage:
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_total: int | None = None
    cost_usd: float | None = None

    @property
    def known(self) -> bool:
        return any(
            value is not None
            for value in (
                self.tokens_in,
                self.tokens_out,
                self.tokens_total,
                self.cost_usd,
            )
        )

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_total": self.tokens_total,
            "cost_usd": self.cost_usd,
        }


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


def _add_int(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return int(left or 0) + int(right or 0)


def _add_float(left: float | None, right: float | None) -> float | None:
    if left is None and right is None:
        return None
    return round(float(left or 0.0) + float(right or 0.0), 6)


def _normalize_model_id(model: str | None) -> str:
    raw = (model or "").strip().lower()
    if not raw:
        return ""
    if "/" in raw:
        raw = raw.split("/")[-1]
    return raw


def estimate_usage_cost_usd(model: str | None, usage: Usage | None) -> float | None:
    """Estimate dollars from token counts when the API omitted cost."""
    if usage is None or usage.cost_usd is not None:
        return usage.cost_usd if usage else None
    key = _normalize_model_id(model)
    if not key:
        return None
    prices = _MODEL_USD_PER_MILLION.get(key)
    if prices is None:
        best: tuple[str, tuple[float, float]] | None = None
        for name, rate in _MODEL_USD_PER_MILLION.items():
            if (key.startswith(name) or name.startswith(key)) and (
                best is None or len(name) > len(best[0])
            ):
                best = (name, rate)
        if best is not None:
            prices = best[1]
    if prices is None:
        return None
    tin = int(usage.tokens_in or 0)
    tout = int(usage.tokens_out or 0)
    if tin == 0 and tout == 0 and usage.tokens_total is None:
        return None
    if tin == 0 and tout == 0 and usage.tokens_total is not None:
        tin = int(usage.tokens_total)
    cost = (tin * prices[0] + tout * prices[1]) / 1_000_000.0
    return round(cost, 6)


def normalize_judge_api_usage(
    data: Any,
    *,
    model: str | None = None,
) -> dict[str, float | int | None] | None:
    """Flatten Decisions / chat usage + optional cost fields from an API response."""
    if not isinstance(data, dict):
        return None
    merged = Usage()
    parts: list[dict[str, Any]] = []
    usage = data.get("usage")
    if isinstance(usage, dict):
        parts.append(usage)
    top_level = {
        key: data[key]
        for key in (*_IN_KEYS, *_OUT_KEYS, *_TOTAL_KEYS, *_COST_KEYS)
        if key in data
    }
    if top_level:
        parts.append(top_level)
    parts.append(data)
    for part in parts:
        parsed = usage_from_mapping(part)
        if parsed is not None:
            merged = merge_usage(merged, parsed) if merged.known else parsed
    if not merged.known:
        return None
    resolved_model = str(data.get("model") or model or "").strip() or None
    if merged.cost_usd is None:
        estimated = estimate_usage_cost_usd(resolved_model, merged)
        if estimated is not None:
            merged = Usage(
                tokens_in=merged.tokens_in,
                tokens_out=merged.tokens_out,
                tokens_total=merged.tokens_total,
                cost_usd=estimated,
            )
    return merged.to_dict()


def combine_task_usage(
    agent: dict[str, Any] | None,
    judged: dict[str, Any] | None,
    *,
    agent_model: str | None = None,
    judge_model: str | None = None,
    agent_subscription: bool = False,
) -> dict[str, Any] | None:
    """Merge harness usage with the judge call's usage for check results."""
    agent_u = usage_from_mapping(agent)
    judge_raw = judged.get("usage") if isinstance(judged, dict) else None
    judge_u = usage_from_mapping(judge_raw)
    if agent_u is None and judge_u is None:
        return agent
    if agent_subscription and agent_u is not None:
        agent_u = Usage(
            tokens_in=agent_u.tokens_in,
            tokens_out=agent_u.tokens_out,
            tokens_total=agent_u.tokens_total,
            cost_usd=None,
        )
    elif agent_u is not None and agent_u.cost_usd is None:
        est = estimate_usage_cost_usd(agent_model, agent_u)
        if est is not None:
            agent_u = Usage(
                tokens_in=agent_u.tokens_in,
                tokens_out=agent_u.tokens_out,
                tokens_total=agent_u.tokens_total,
                cost_usd=est,
            )
    if judge_u is not None and judge_u.cost_usd is None:
        jmodel = judge_model
        if isinstance(judged, dict) and not jmodel:
            jmodel = str(judged.get("model") or "").strip() or None
        est = estimate_usage_cost_usd(jmodel, judge_u)
        if est is not None:
            judge_u = Usage(
                tokens_in=judge_u.tokens_in,
                tokens_out=judge_u.tokens_out,
                tokens_total=judge_u.tokens_total,
                cost_usd=est,
            )
    agent_cost = agent_u.cost_usd if agent_u else None
    judge_cost = judge_u.cost_usd if judge_u else None
    total_cost = _add_float(agent_cost, judge_cost)
    out: dict[str, Any] = {
        "tokens_in": _add_int(
            agent_u.tokens_in if agent_u else None,
            judge_u.tokens_in if judge_u else None,
        ),
        "tokens_out": _add_int(
            agent_u.tokens_out if agent_u else None,
            judge_u.tokens_out if judge_u else None,
        ),
        "tokens_total": _add_int(
            agent_u.tokens_total if agent_u else None,
            judge_u.tokens_total if judge_u else None,
        ),
        "cost_usd": total_cost,
    }
    if agent_cost is not None:
        out["agent_cost_usd"] = agent_cost
    if judge_cost is not None:
        out["judge_cost_usd"] = judge_cost
    tokens_seen = (
        out.get("tokens_total") is not None
        or out.get("tokens_in") is not None
        or out.get("tokens_out") is not None
    )
    if agent_subscription:
        out["agent_cost_label"] = SUBSCRIPTION_COST_LABEL
    if tokens_seen and total_cost is None and not agent_subscription:
        out["cost_unknown"] = True
    elif total_cost is not None:
        out.pop("cost_unknown", None)
    return {key: value for key, value in out.items() if value is not None}


def is_non_content_stream_line(raw: str) -> bool:
    """True for rate-limit, system/init, and other non-content stream events."""
    text = raw.strip()
    if not text.startswith("{"):
        return False
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return False
    if not isinstance(obj, dict):
        return False
    return str(obj.get("type") or "") in _NON_CONTENT_EVENTS


def render_stream_line(raw: str) -> str | None:
    """Human-readable live-tail line; None drops harness bookkeeping rows."""
    text = raw.strip()
    if not text.startswith("{"):
        return raw
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return raw
    if not isinstance(obj, dict):
        return raw
    kind = obj.get("type")
    if kind in _CODEX_BOOKKEEPING or kind == "item.started":
        return None
    if kind == "item.completed":
        return _render_codex_item(obj.get("item"))
    if kind == "user":
        return _render_claude_tool_results(obj)
    if kind in _CURSOR_BOOKKEEPING:
        # Cursor init/user echo/final result: no human line (usage still parsed
        # by `parse_usage_line`, which runs before this render in the sink).
        return None
    if kind == "thinking":
        return _render_cursor_thinking(obj)
    if kind == "assistant":
        return _render_cursor_assistant(obj.get("message"))
    if kind == "tool_call":
        return _render_cursor_tool_call(obj)
    if kind == "error":
        message = obj.get("message") or obj.get("error")
        return f"error: {message}" if message else "error"
    if kind == "event_msg":
        payload = obj.get("payload")
        if isinstance(payload, dict) and payload.get("type") == "token_count":
            return None
        return raw
    if kind in _NON_CONTENT_EVENTS:
        return None
    return raw


def _pick(current: float | None, update: float | None) -> float | None:
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


def _render_codex_item(item: Any) -> str | None:
    if not isinstance(item, dict):
        return None
    itype = item.get("type")
    if itype == "agent_message":
        text = str(item.get("text") or "").strip()
        return text or None
    if itype == "command_execution":
        command = str(item.get("command") or "").strip()
        return f"$ {command}" if command else None
    if itype == "file_change":
        changes = item.get("changes")
        paths = [
            str(change["path"])
            for change in changes or []
            if isinstance(change, dict) and change.get("path")
        ]
        return "changed " + ", ".join(paths) if paths else None
    if itype == "reasoning":
        text = str(item.get("text") or "").strip()
        return text or None
    return None


# --- Cursor Agent (`--output-format stream-json`) ---

# Argument fields worth surfacing first, so a tool line reads like a command.
_CURSOR_ARG_KEYS = ("command", "path", "globPattern", "pattern", "query", "file_path")


def _render_cursor_thinking(obj: dict[str, Any]) -> str | None:
    text = str(obj.get("text") or "").strip()
    return text or None


def _render_cursor_assistant(message: Any) -> str | None:
    if not isinstance(message, dict):
        return None
    parts = message.get("content")
    if not isinstance(parts, list):
        return None
    lines: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "text":
            text = str(part.get("text") or "").strip()
            if text:
                lines.append(text)
        elif part.get("type") == "tool_use":
            command = _claude_tool_command(part)
            if command:
                lines.append(f"$ {command}")
    return "\n".join(lines) or None


def _claude_tool_command(part: dict[str, Any]) -> str:
    name = str(part.get("name") or "tool").strip() or "tool"
    args = part.get("input") if isinstance(part.get("input"), dict) else {}
    detail = ""
    for key in ("command", "cmd", "script", "file_path", "path", "pattern", "query"):
        value = args.get(key) if isinstance(args, dict) else None
        if isinstance(value, str) and value.strip():
            detail = value.strip()
            break
    if name.lower() in {"bash", "shell", "run"} and detail:
        return detail
    return f"{name} {detail}".strip()


def _render_claude_tool_results(obj: dict[str, Any]) -> str | None:
    message = obj.get("message")
    parts = message.get("content") if isinstance(message, dict) else None
    if not isinstance(parts, list):
        return None
    lines: list[str] = []
    for part in parts:
        if not isinstance(part, dict) or part.get("type") != "tool_result":
            continue
        text = _claude_tool_result_text(part.get("content"))
        if text:
            lines.append(text[:2500])
    return "\n".join(lines) or None


def _claude_tool_result_text(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, list):
        bits: list[str] = []
        for item in raw:
            if isinstance(item, str) and item.strip():
                bits.append(item.strip())
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str) and text.strip():
                    bits.append(text.strip())
        return "\n".join(bits)
    if isinstance(raw, dict):
        text = raw.get("text") or raw.get("content") or raw.get("stdout")
        if isinstance(text, str):
            return text.strip()
    return ""


def _render_cursor_tool_call(obj: dict[str, Any]) -> str | None:
    # Show the invocation once; the completed envelope would echo the result.
    if obj.get("subtype") == "completed":
        return None
    call = obj.get("tool_call")
    if not isinstance(call, dict):
        return None
    for name, payload in call.items():
        if not name.endswith("ToolCall") or not isinstance(payload, dict):
            continue
        label = name[: -len("ToolCall")].lower()
        summary = _cursor_tool_args(payload.get("args"))
        return f"$ {label} {summary}".rstrip() if summary else f"$ {label}"
    return None


def _cursor_tool_args(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    for key in _CURSOR_ARG_KEYS:
        value = args.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    for value in args.values():
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip()
    return ""
