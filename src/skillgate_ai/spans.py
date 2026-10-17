"""OTLP-shaped span records for check timelines.

Harness adapters (Codex JSONL, Cursor stream-json) emit vendor events; we map
them into a small OpenTelemetry-compatible span list. The Gate UI prefers these
spans over heuristic transcript parsing. No collector required — records live
on the TaskReport and can export OTLP later.
"""

from __future__ import annotations

import json
import secrets
import time
from pathlib import PurePosixPath
from typing import Any

# OTel status codes: https://opentelemetry.io/docs/specs/otel/trace/api/#set-status
STATUS_UNSET = 0
STATUS_OK = 1
STATUS_ERROR = 2

# SpanKind INTERNAL
KIND_INTERNAL = 1


def _id(nbytes: int = 8) -> str:
    return secrets.token_hex(nbytes)


def _now_ns() -> int:
    return time.time_ns()


def _attr(key: str, value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"key": key, "value": {"boolValue": value}}
    if isinstance(value, int) and not isinstance(value, bool):
        return {"key": key, "value": {"intValue": str(value)}}
    if isinstance(value, float):
        return {"key": key, "value": {"doubleValue": value}}
    return {"key": key, "value": {"stringValue": str(value)}}


def make_span(
    *,
    name: str,
    trace_id: str,
    parent_span_id: str | None = None,
    span_id: str | None = None,
    start_ns: int | None = None,
    end_ns: int | None = None,
    status: int = STATUS_OK,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One OTLP JSON span (trimmed — enough for UI + future export)."""
    start = start_ns if start_ns is not None else _now_ns()
    end = end_ns if end_ns is not None else start
    attrs = [_attr(k, v) for k, v in (attributes or {}).items() if v is not None]
    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id or _id(8),
        "name": name,
        "kind": KIND_INTERNAL,
        "startTimeUnixNano": str(start),
        "endTimeUnixNano": str(end),
        "status": {"code": status},
        "attributes": attrs,
    }
    if parent_span_id:
        span["parentSpanId"] = parent_span_id
    return span


def _basename(path: str) -> str:
    return PurePosixPath(path.replace("\\", "/")).name


def _cursor_tool_span(
    obj: dict[str, Any], *, trace_id: str, parent: str, t_ns: int
) -> dict[str, Any] | None:
    if obj.get("subtype") == "completed":
        return None
    call = obj.get("tool_call")
    if not isinstance(call, dict):
        return None
    for name, payload in call.items():
        if not name.endswith("ToolCall") or not isinstance(payload, dict):
            continue
        tool = name[: -len("ToolCall")].lower()
        args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
        summary = ""
        path = ""
        for key in ("command", "path", "globPattern", "pattern", "query", "file_path"):
            value = args.get(key) if isinstance(args, dict) else None
            if isinstance(value, str) and value.strip():
                summary = value.strip()
                if key in {"path", "file_path"}:
                    path = value.strip()
                break
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool,
        }
        if summary:
            attrs["gen_ai.tool.call.arguments"] = summary[:500]
        if path:
            attrs["file.path"] = path
            attrs["file.name"] = _basename(path)
        # Map common tools to stable span names (industry-ish, harness-neutral)
        if tool in {"shell", "bash", "run"}:
            span_name = "tool.shell"
        elif tool in {"read", "readfile", "read_file"}:
            span_name = "tool.read"
        elif tool in {"write", "edit", "searchreplace", "applypatch"}:
            span_name = "tool.write"
        elif tool in {"glob", "grep", "rg", "search"}:
            span_name = "tool.search"
        else:
            span_name = f"tool.{tool}"
        return make_span(
            name=span_name,
            trace_id=trace_id,
            parent_span_id=parent,
            start_ns=t_ns,
            end_ns=t_ns,
            attributes=attrs,
        )
    return None


def _codex_item_span(
    item: Any, *, trace_id: str, parent: str, t_ns: int
) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    itype = item.get("type")
    if itype == "command_execution":
        command = str(item.get("command") or "").strip()
        return make_span(
            name="tool.shell",
            trace_id=trace_id,
            parent_span_id=parent,
            start_ns=t_ns,
            end_ns=t_ns,
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": "shell",
                "gen_ai.tool.call.arguments": command[:500],
            },
        )
    if itype == "file_change":
        changes = item.get("changes") or []
        paths = [
            str(change["path"])
            for change in changes
            if isinstance(change, dict) and change.get("path")
        ]
        path = paths[0] if paths else ""
        name = "skill.select" if path.endswith("selected.json") or "catalog.md" in path else "tool.write"
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": "write",
        }
        if path:
            attrs["file.path"] = path
            attrs["file.name"] = _basename(path)
        if len(paths) > 1:
            attrs["file.paths"] = ", ".join(paths[:8])
        return make_span(
            name=name,
            trace_id=trace_id,
            parent_span_id=parent,
            start_ns=t_ns,
            end_ns=t_ns,
            attributes=attrs,
        )
    if itype == "agent_message":
        text = str(item.get("text") or "").strip()
        if not text:
            return None
        return make_span(
            name="gen_ai.assistant",
            trace_id=trace_id,
            parent_span_id=parent,
            start_ns=t_ns,
            end_ns=t_ns,
            attributes={
                "gen_ai.operation.name": "chat",
                "gen_ai.assistant.message": text[:ASSISTANT_MSG_MAX],
            },
        )
    return None



ASSISTANT_MSG_MAX = 2000


def _assistant_text(obj: dict[str, Any]) -> str:
    msg = obj.get("message")
    bits: list[str] = []
    if isinstance(msg, dict) and isinstance(msg.get("content"), list):
        for part in msg["content"]:
            if isinstance(part, dict) and part.get("type") == "text":
                bit = str(part.get("text") or "")
                if bit:
                    bits.append(bit)
    return "".join(bits) if bits else ""


def _is_cursor_partial_assistant(obj: dict[str, Any]) -> bool:
    """Cursor --stream-partial-output delta (append; do not open a new step).

    Docs: timestamp_ms present + no model_call_id → streaming delta.
    model_call_id → buffered duplicate before a tool call (skip).
    no timestamp_ms after partials → final flush duplicate (skip).
    """
    return "timestamp_ms" in obj and "model_call_id" not in obj


def _is_cursor_assistant_dup_flush(obj: dict[str, Any], *, had_partial: bool) -> bool:
    if "model_call_id" in obj:
        return True
    # Final flush at end of a streamed message (no timestamp_ms).
    if had_partial and "timestamp_ms" not in obj:
        return True
    return False



def _glue_assistant_delta(prev: str, delta: str) -> str:
    """Join streamed assistant chunks. Cursor may omit the leading space on words."""
    if not prev:
        return delta
    if not delta:
        return prev
    if prev[-1].isspace() or delta[0].isspace():
        return prev + delta
    # Punctuation / markdown / path glue — never insert a space.
    if delta[0] in ".,!?;:)]}`*_/":
        return prev + delta
    if prev[-1] in "([{/`*_":
        return prev + delta
    return prev + " " + delta

def _set_string_attr(span: dict[str, Any], key: str, value: str) -> None:
    attrs = span.setdefault("attributes", [])
    for item in attrs:
        if isinstance(item, dict) and item.get("key") == key:
            item["value"] = {"stringValue": value}
            return
    attrs.append({"key": key, "value": {"stringValue": value}})


def _claude_tool_spans(
    obj: dict[str, Any], *, trace_id: str, parent: str, t_ns: int
) -> list[dict[str, Any]]:
    """Claude Code stream-json tool_use blocks (Bash and others) as tool spans."""
    parts: list[dict[str, Any]] = []
    if obj.get("type") == "tool_use":
        parts = [obj]
    else:
        message = obj.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            parts = [
                part
                for part in content
                if isinstance(part, dict) and part.get("type") == "tool_use"
            ]
    spans: list[dict[str, Any]] = []
    for part in parts:
        name = str(part.get("name") or "tool").strip() or "tool"
        args = part.get("input") if isinstance(part.get("input"), dict) else {}
        summary = ""
        path = ""
        for key in ("command", "cmd", "script", "file_path", "path", "pattern", "query"):
            value = args.get(key) if isinstance(args, dict) else None
            if isinstance(value, str) and value.strip():
                summary = value.strip()
                if key in {"path", "file_path"}:
                    path = value.strip()
                break
        tool = name.lower()
        if tool in {"bash", "shell", "run"}:
            span_name = "tool.shell"
        elif tool in {"read", "readfile", "read_file"}:
            span_name = "tool.read"
        elif tool in {"write", "edit", "searchreplace", "applypatch"}:
            span_name = "tool.write"
        elif tool in {"glob", "grep", "rg", "search"}:
            span_name = "tool.search"
        else:
            span_name = f"tool.{tool}"
        if tool not in {"bash", "shell", "run"} and summary:
            summary = f"{name} {summary}".strip()
        attrs: dict[str, Any] = {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool,
        }
        if summary:
            attrs["gen_ai.tool.call.arguments"] = summary[:500]
        if path:
            attrs["file.path"] = path
            attrs["file.name"] = _basename(path)
        spans.append(
            make_span(
                name=span_name,
                trace_id=trace_id,
                parent_span_id=parent,
                start_ns=t_ns,
                end_ns=t_ns,
                attributes=attrs,
            )
        )
    return spans


def spans_from_jsonl(stdout: str, *, trace_id: str | None = None) -> list[dict[str, Any]]:
    """Map Codex/Cursor JSONL stdout into OTLP-shaped spans (order preserved)."""
    tid = trace_id or _id(16)
    root_id = _id(8)
    t0 = _now_ns()
    spans: list[dict[str, Any]] = [
        make_span(
            name="eval.check",
            trace_id=tid,
            span_id=root_id,
            start_ns=t0,
            end_ns=t0,
            attributes={"gen_ai.operation.name": "invoke_agent"},
        )
    ]
    tick = t0
    open_assistant_idx: int | None = None
    pending_open_assistant = False
    for raw in stdout.splitlines():
        text = raw.strip()
        if not text.startswith("{"):
            continue
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        tick += 1_000_000  # 1ms separation for ordering when clocks absent
        kind = obj.get("type")
        span: dict[str, Any] | None = None
        pending_open_assistant = False
        extra: list[dict[str, Any]] = []
        if kind == "tool_call":
            span = _cursor_tool_span(obj, trace_id=tid, parent=root_id, t_ns=tick)
        elif kind == "item.completed":
            span = _codex_item_span(obj.get("item"), trace_id=tid, parent=root_id, t_ns=tick)
        elif kind in {"error", "turn.failed"}:
            if kind == "error":
                msg = str(obj.get("message") or "").strip()
            else:
                err = obj.get("error")
                if isinstance(err, dict):
                    msg = str(err.get("message") or "").strip()
                else:
                    msg = str(err or "").strip()
            if msg:
                span = make_span(
                    name="gen_ai.error",
                    trace_id=tid,
                    parent_span_id=root_id,
                    start_ns=tick,
                    end_ns=tick,
                    status=STATUS_ERROR,
                    attributes={
                        "gen_ai.operation.name": "error",
                        "error.message": msg[:400],
                    },
                )
        elif kind in {"user", "tool_use"}:
            extra = _claude_tool_spans(obj, trace_id=tid, parent=root_id, t_ns=tick)
        elif kind == "assistant":
            extra = _claude_tool_spans(obj, trace_id=tid, parent=root_id, t_ns=tick)
            # Cursor --stream-partial-output emits one assistant event per token.
            # Coalesce consecutive partial deltas into one growing gen_ai.assistant
            # span; open a new Assistant step only after a tool (or other) step.
            joined = _assistant_text(obj)
            if not joined:
                span = None
            elif _is_cursor_assistant_dup_flush(obj, had_partial=open_assistant_idx is not None):
                span = None
            elif _is_cursor_partial_assistant(obj) and open_assistant_idx is not None:
                prev = spans[open_assistant_idx]
                prev_msg = str(attr_map(prev).get("gen_ai.assistant.message") or "")
                _set_string_attr(
                    prev, "gen_ai.assistant.message", _glue_assistant_delta(prev_msg, joined)[:ASSISTANT_MSG_MAX]
                )
                prev["endTimeUnixNano"] = str(tick)
                span = None
            elif _is_cursor_partial_assistant(obj):
                span = make_span(
                    name="gen_ai.assistant",
                    trace_id=tid,
                    parent_span_id=root_id,
                    start_ns=tick,
                    end_ns=tick,
                    attributes={
                        "gen_ai.operation.name": "chat",
                        "gen_ai.assistant.message": joined[:ASSISTANT_MSG_MAX],
                    },
                )
                # Stash index after append below.
                pending_open_assistant = True
            else:
                # Complete assistant message (no stream-partial / Codex-style).
                span = make_span(
                    name="gen_ai.assistant",
                    trace_id=tid,
                    parent_span_id=root_id,
                    start_ns=tick,
                    end_ns=tick,
                    attributes={
                        "gen_ai.operation.name": "chat",
                        "gen_ai.assistant.message": joined[:ASSISTANT_MSG_MAX],
                    },
                )
                open_assistant_idx = None
                pending_open_assistant = False
        if kind == "tool_call" or kind == "item.completed" or extra:
            # Next assistant (partial or complete) starts a new step.
            open_assistant_idx = None
            pending_open_assistant = False
        if extra:
            spans.extend(extra)
        if span is not None:
            spans.append(span)
            if pending_open_assistant:
                open_assistant_idx = len(spans) - 1
                pending_open_assistant = False
    # Close root
    if len(spans) > 1:
        spans[0]["endTimeUnixNano"] = spans[-1]["endTimeUnixNano"]
    return spans


def attr_map(span: dict[str, Any]) -> dict[str, Any]:
    """Flatten OTLP attributes for UI / tests."""
    out: dict[str, Any] = {}
    for item in span.get("attributes") or []:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        value = item.get("value")
        if not isinstance(key, str) or not isinstance(value, dict):
            continue
        if "stringValue" in value:
            out[key] = value["stringValue"]
        elif "intValue" in value:
            out[key] = int(value["intValue"])
        elif "doubleValue" in value:
            out[key] = float(value["doubleValue"])
        elif "boolValue" in value:
            out[key] = bool(value["boolValue"])
    return out
