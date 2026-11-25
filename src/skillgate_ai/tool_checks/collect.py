from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from skillgate_ai.span_facts import _parse_calls_log, _span_invokes
from skillgate_ai.spans import attr_map, spans_from_jsonl
from skillgate_ai.tool_check_schema import DEFAULT_CALLS_LOG
from skillgate_ai.tool_checks.aliases import ToolCall, _shell_rule_aliases, tool_aliases
from skillgate_ai.tool_checks.rules import (
    _ENV_PREFIX,
    _INTERPRETERS,
    _SEP,
    _SHELL_RULES,
    _SHELL_TOOLS,
    _SUDO_PREFIX,
)


def _args_from_row(row: Mapping[str, Any]) -> dict[str, Any] | str:
    raw = row.get("args")
    if raw is None:
        raw = row.get("params")
    if isinstance(raw, dict):
        return raw
    if raw is not None:
        return str(raw)
    argv = row.get("argv")
    if isinstance(argv, str):
        parts = argv.split()
    elif isinstance(argv, Sequence):
        parts = [str(item) for item in argv]
    else:
        return ""
    if len(parts) > 1:
        return " ".join(parts[1:])
    return ""


def _name_from_argv(argv: Sequence[str]) -> str | None:
    parts = [str(item) for item in argv]
    idx = 0
    while idx < len(parts):
        token = parts[idx].lower()
        base = Path(parts[idx]).name.lower()
        if token in _INTERPRETERS or base in _INTERPRETERS:
            idx += 1
            while idx < len(parts) and parts[idx].startswith("-"):
                idx += 1
            continue
        if parts[idx].startswith("-"):
            idx += 1
            continue
        stem = Path(parts[idx]).stem
        extra: list[str] = []
        j = idx + 1
        while j < len(parts) and not parts[j].startswith("-") and len(extra) < 2:
            if "/" not in parts[j] and "." not in parts[j]:
                extra.append(parts[j])
            j += 1
        name = stem
        if extra:
            name = "_".join([stem, *extra[:3]])
        return name
    return None


def _name_from_row(row: Mapping[str, Any]) -> str | None:
    for key in ("tool", "name"):
        raw = row.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    argv = row.get("argv")
    if isinstance(argv, str):
        argv = argv.split()
    if isinstance(argv, Sequence) and argv:
        return _name_from_argv(argv)
    return None


def _shell_segments(command: str) -> list[str]:
    return [seg.strip() for seg in _SEP.split(command or "") if seg.strip()]


def _command_stem(segment: str) -> str:
    """Leading command after optional sudo / env assignments."""
    stem = segment.strip()
    while stem:
        sudo = _SUDO_PREFIX.match(stem)
        if sudo:
            stem = stem[sudo.end() :].lstrip()
            continue
        env = _ENV_PREFIX.match(stem)
        if env:
            stem = stem[env.end() :].lstrip()
            continue
        break
    return stem


def _shell_rule_calls(command: str) -> list[ToolCall]:
    out: list[ToolCall] = []
    for segment in _shell_segments(command):
        stem = _command_stem(segment)
        if not stem:
            continue
        for rule_id, pattern in _SHELL_RULES:
            seg_lower = stem.lower()
            if "what-if" in seg_lower or "what_if" in seg_lower:
                continue
            if (
                rule_id == "shell:az_mutate"
                and stem.lower().startswith("az ")
                and re.match(r"\b(show|list|validate)\b", stem, re.I)
            ):
                continue
            if pattern.match(stem):
                label = f"shell: {segment[:80]}"
                aliases = _shell_rule_aliases(rule_id)
                out.append(
                    ToolCall(
                        name=rule_id,
                        aliases=aliases,
                        args=segment,
                        source="shell",
                        label=label,
                    )
                )
                break
    return out


def _declared_shell_calls(command: str, declared: Iterable[str]) -> list[ToolCall]:
    out: list[ToolCall] = []
    for segment in _shell_segments(command):
        for name in declared:
            if _span_invokes("shell", segment, name):
                label = f"shell: {segment[:80]}"
                out.append(
                    ToolCall(
                        name=name,
                        aliases=tool_aliases(name),
                        args=segment,
                        source="shell",
                        label=label,
                    )
                )
    return out


def _args_from_span(attrs: Mapping[str, str]) -> dict[str, Any] | str:
    raw = str(attrs.get("gen_ai.tool.call.arguments") or "")
    if not raw:
        return ""
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return raw


def _safe_calls_log_path(workspace: Path, calls_log: str) -> Path | None:
    rel = calls_log.replace("\\", "/").lstrip("/")
    if ".." in Path(rel).parts:
        return None
    target = (workspace / rel).resolve()
    try:
        target.relative_to(workspace.resolve())
    except ValueError:
        return None
    return target


def collect_tool_calls(
    workspace: Path,
    spans: Sequence[Mapping[str, Any]] | None,
    transcript: str,
    *,
    calls_log: str = DEFAULT_CALLS_LOG,
    declared: Iterable[str] = (),
) -> list[ToolCall]:
    calls: list[ToolCall] = []
    log_path = _safe_calls_log_path(workspace, calls_log)
    if log_path is not None and log_path.is_file():
        text = log_path.read_text(encoding="utf-8", errors="replace")
        for row in _parse_calls_log(text):
            name = _name_from_row(row)
            if not name:
                continue
            calls.append(
                ToolCall(
                    name=name,
                    aliases=tool_aliases(name),
                    args=_args_from_row(row),
                    source="calls_log",
                    label=calls_log,
                )
            )

    records = list(spans or [])
    has_tool_span = any(
        isinstance(item, Mapping)
        and str(attr_map(dict(item)).get("gen_ai.tool.name") or "").strip()
        for item in records
    )
    if not has_tool_span and transcript:
        records = list(spans_from_jsonl(transcript) or [])

    declared_list = list(declared)
    for span in records:
        if not isinstance(span, Mapping):
            continue
        attrs = attr_map(dict(span))
        tool = str(attrs.get("gen_ai.tool.name") or "").strip()
        if not tool:
            continue
        args = _args_from_span(attrs)
        if tool.lower() in _SHELL_TOOLS:
            raw_args = attrs.get("gen_ai.tool.call.arguments") or ""
            command = args if isinstance(args, str) else str(raw_args)
            calls.extend(_declared_shell_calls(command, declared_list))
            calls.extend(_shell_rule_calls(command))
            continue
        calls.append(
            ToolCall(
                name=tool,
                aliases=tool_aliases(tool),
                args=args,
                source="span",
                label="tool span",
            )
        )
    return calls
