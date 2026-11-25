from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from skillgate_ai.span_facts.patterns import _INVOKE_TOOLS, _WORD, _WRITE_PAYLOAD
from skillgate_ai.spans import attr_map


def count_tool_calls(
    spans: Sequence[Mapping[str, Any]] | None,
    name: str,
    *,
    trajectory: Mapping[str, Any] | None = None,
) -> int:
    """How many times ``name`` was invoked, not merely mentioned in a write."""
    token = (name or "").strip()
    if not token:
        return 0
    count = 0
    for span in spans or []:
        if not isinstance(span, Mapping):
            continue
        attrs = attr_map(dict(span))
        tool = str(attrs.get("gen_ai.tool.name") or "")
        args = str(attrs.get("gen_ai.tool.call.arguments") or "")
        if _span_invokes(tool, args, token):
            count += 1
    if count or not trajectory:
        return count
    for row in trajectory.get("commands") or []:
        if not isinstance(row, Mapping):
            continue
        tool = str(row.get("tool") or "")
        args = str(row.get("args") or "")
        if _span_invokes(tool, args, token):
            count += 1
    return count


def _span_invokes(tool: str, args: str, token: str) -> bool:
    called = (tool or "").strip().lower()
    name = (token or "").strip().lower()
    if not name:
        return False
    if called == name:
        return True
    if _WRITE_PAYLOAD.search(args or ""):
        return False
    if called and called not in _INVOKE_TOOLS:
        return False
    return bool(re.search(_WORD.format(name=re.escape(name)), args or "", re.IGNORECASE))


def tool_results(
    spans: Sequence[Mapping[str, Any]] | None,
    name: str,
    *,
    trajectory: Mapping[str, Any] | None = None,
) -> list[str]:
    """Captured outputs for ``name``, when the log recorded them."""
    token = (name or "").strip()
    if not token:
        return []
    pat = re.compile(_WORD.format(name=re.escape(token)))
    out: list[str] = []
    for span in spans or []:
        if not isinstance(span, Mapping):
            continue
        attrs = attr_map(dict(span))
        tool = str(attrs.get("gen_ai.tool.name") or "")
        args = str(attrs.get("gen_ai.tool.call.arguments") or "")
        result = str(attrs.get("gen_ai.tool.call.result") or "").strip()
        if not result:
            continue
        if tool == token or pat.search(f"{tool} {args}"):
            out.append(result)
    if out or not trajectory:
        return out
    for row in trajectory.get("command_runs") or []:
        if not isinstance(row, Mapping):
            continue
        command = str(row.get("command") or "")
        output = str(row.get("output") or "").strip()
        if output and pat.search(command):
            out.append(output)
    return out


def count_file_reads(
    spans: Sequence[Mapping[str, Any]] | None,
    name: str,
    *,
    trajectory: Mapping[str, Any] | None = None,
    tool: str | None = None,
) -> int:
    """How many logged calls mentioned ``name`` (a file like status.txt)."""
    token = (name or "").strip()
    if not token:
        return 0
    needle = token.lower()
    tool_name = (tool or "").strip().lower()
    count = 0
    for span in spans or []:
        if not isinstance(span, Mapping):
            continue
        attrs = attr_map(dict(span))
        called = str(attrs.get("gen_ai.tool.name") or "").strip().lower()
        args = str(attrs.get("gen_ai.tool.call.arguments") or "")
        path = str(attrs.get("file.path") or "")
        blob = f"{args} {path}".lower()
        if needle not in blob:
            continue
        if tool_name and called and called != tool_name and tool_name not in blob:
            continue
        count += 1
    if count or not trajectory:
        return count
    for row in trajectory.get("commands") or []:
        if not isinstance(row, Mapping):
            continue
        blob = f"{row.get('tool') or ''} {row.get('args') or ''} {row.get('file') or ''}"
        if needle not in blob.lower():
            continue
        if tool_name and tool_name not in blob.lower():
            continue
        count += 1
    return count
