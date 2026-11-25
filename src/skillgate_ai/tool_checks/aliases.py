from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Any, Literal


@dataclass(frozen=True)
class ToolCall:
    name: str
    aliases: frozenset[str]
    args: dict[str, Any] | str
    source: Literal["calls_log", "span", "shell"]
    label: str


def normalize_tool_name(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if text.lower().startswith("mcp__"):
        parts = text.split("__")
        if len(parts) >= 3:
            return "__".join(parts).lower()
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", text)
    text = re.sub(r"[-./\s]+", "_", text)
    text = text.lower()
    while "__" in text and not text.startswith("mcp__"):
        text = text.replace("__", "_")
    text = re.sub(r"_+", "_", text).strip("_")
    return text


def tool_aliases(raw: str) -> frozenset[str]:
    norm = normalize_tool_name(raw)
    if not norm:
        return frozenset()
    aliases: set[str] = {norm}
    if norm.startswith("mcp__"):
        parts = norm.split("__")
        if len(parts) >= 3:
            aliases.add(norm)
            aliases.add("__".join(parts[1:]))
            aliases.add(parts[-1])
            if len(parts) >= 3:
                aliases.add(f"{parts[-2]}_{parts[-1]}")
    else:
        segments = [seg for seg in norm.split("_") if seg]
        for idx in range(len(segments)):
            aliases.add("_".join(segments[idx:]))
    return frozenset(aliases)


def _shell_rule_aliases(rule_id: str) -> frozenset[str]:
    if not rule_id.startswith("shell:"):
        return frozenset({rule_id})
    tail = rule_id.removeprefix("shell:")
    spaced = tail.replace("_", " ")
    return frozenset({rule_id, tail, spaced})


def _pattern_forms(pattern: str) -> set[str]:
    raw = (pattern or "").strip()
    if not raw:
        return set()
    forms = {raw, normalize_tool_name(raw)}
    if " " in raw:
        forms.add(raw.lower())
        forms.add(raw.replace(" ", "_").lower())
    return {item for item in forms if item}


def matches_pattern(call: ToolCall, pattern: str) -> bool:
    pat = normalize_tool_name(pattern)
    forms = _pattern_forms(pattern)
    alias_l = {alias.lower() for alias in call.aliases}
    if forms & alias_l:
        return True
    if not pat:
        return False
    for alias in call.aliases:
        if fnmatch.fnmatchcase(alias, pat):
            return True
        if alias == pat:
            return True
    return False
