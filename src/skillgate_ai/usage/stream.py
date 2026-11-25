from __future__ import annotations

import json
from typing import Any

from skillgate_ai.usage.model import (
    _CODEX_BOOKKEEPING,
    _CURSOR_BOOKKEEPING,
    _NON_CONTENT_EVENTS,
)


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
