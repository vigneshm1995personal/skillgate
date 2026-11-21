"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import json
from typing import Any

from skillgate_ai.spans import spans_from_jsonl
from skillgate_ai.usage import (
    render_stream_line,
)


def _claude_used_model(stdout: str) -> str | None:
    """Model Claude Code actually used, from stream-json output.

    The final ``result`` message carries ``modelUsage`` (keys are model ids);
    the ``system`` init message carries a top-level ``model`` field as a
    fallback for runs that never emit a result envelope.
    """
    fallback: str | None = None
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        kind = obj.get("type")
        if kind == "system" and isinstance(obj.get("model"), str):
            fallback = str(obj["model"]).strip() or fallback
        if kind == "result" and isinstance(obj.get("modelUsage"), dict):
            chosen = _busiest_model_usage(obj["modelUsage"])
            if chosen:
                return chosen
    return fallback


def _busiest_model_usage(model_usage: dict[str, Any]) -> str | None:
    """Model id that did the work. A side model listed first must not win."""
    best_id: str | None = None
    best_tokens = -1
    for model_id, stats in model_usage.items():
        if not isinstance(model_id, str) or not model_id.strip():
            continue
        tokens = 0
        if isinstance(stats, dict):
            for key in ("outputTokens", "output_tokens", "inputTokens", "input_tokens"):
                value = stats.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    tokens += int(value)
        if tokens > best_tokens:
            best_tokens = tokens
            best_id = model_id.strip()
    return best_id


def _codex_used_model(stdout: str, default: str | None) -> str | None:
    """Model Codex actually used: any model id in `--json` output, else the -m flag."""
    for raw in (stdout or "").splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        model_id = obj.get("model") or obj.get("model_id") or obj.get("modelId")
        if isinstance(model_id, str) and model_id.strip():
            return model_id.strip()
    return (default or "").strip() or None


def _jsonl_spans(stdout: str) -> list[dict]:
    """OTLP-shaped spans from the same JSONL that feeds the transcript."""
    return spans_from_jsonl(stdout or "")


def _jsonl_transcript(stdout: str, stderr: str) -> str:
    """Render harness JSONL stdout back to readable lines, then append stderr.

    Used for every JSONL harness (Codex `--json`, Cursor `stream-json`) so
    skill selection, read-path inference, and the transcript the UI shows all
    see the same readable text regardless of adapter.
    """
    lines = [
        rendered
        for rendered in (render_stream_line(line) for line in stdout.splitlines())
        if rendered
    ]
    text = "\n".join(lines)
    if stderr:
        return f"{text}\n{stderr}" if text else stderr
    return text


def _codex_transcript(stdout: str, stderr: str) -> str:
    return _jsonl_transcript(stdout, stderr)


def _cursor_transcript(stdout: str, stderr: str) -> str:
    return _jsonl_transcript(stdout, stderr)
