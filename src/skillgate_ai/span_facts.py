"""Custom checks that are facts in the log, scored from spans instead of the judge."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from skillgate_ai.judge_spec import JudgeQuestion, JudgeSpec
from skillgate_ai.spans import attr_map

_TOOL_TICK = re.compile(r"`([a-z][a-z0-9_-]{2,})`", re.IGNORECASE)
_TOOL_CALLED = re.compile(
    r"\b(?:called|call(?:s|ed|ing)?)\s+`?([a-z][a-z0-9_-]{2,})`?",
    re.IGNORECASE,
)
_SNAKE = re.compile(r"\b([a-z][a-z0-9]*_[a-z0-9_]+)\b")
_MORE_THAN_ONCE = re.compile(r"more than once|duplicate|second (?:call|refund)", re.IGNORECASE)
_ANSWER_NO_IF = re.compile(r"answer\s+no\s+if", re.IGNORECASE)
_REPLY = re.compile(r"\breply\b|\bcustomer (?:says|said|reply)\b", re.IGNORECASE)
_RETURN = re.compile(r"\breturned?\b|\breturns\b|\bresult\b", re.IGNORECASE)
_STATUS = re.compile(
    r"\b(succeeded|success|timeout|timed out|failed|502|error)\b",
    re.IGNORECASE,
)
_WORD = r"(?<![A-Za-z0-9_]){name}(?![A-Za-z0-9_])"
_STOP = frozenset(
    {
        "times",
        "once",
        "status",
        "success",
        "succeeded",
        "result",
        "error",
        "timeout",
        "output",
        "amount",
        "customer",
        "agent",
        "first",
        "second",
        "more",
        "call",
        "calls",
        "called",
        "return",
        "returned",
        "returns",
        "lookup",
        "connector",
    }
)


def count_tool_calls(
    spans: Sequence[Mapping[str, Any]] | None,
    name: str,
    *,
    trajectory: Mapping[str, Any] | None = None,
) -> int:
    """How many times ``name`` was invoked in span args (or trajectory fallback)."""
    token = (name or "").strip()
    if not token:
        return 0
    pat = re.compile(_WORD.format(name=re.escape(token)))
    count = 0
    for span in spans or []:
        if not isinstance(span, Mapping):
            continue
        attrs = attr_map(dict(span))
        tool = str(attrs.get("gen_ai.tool.name") or "")
        args = str(attrs.get("gen_ai.tool.call.arguments") or "")
        if tool == token or pat.search(f"{tool} {args}"):
            count += 1
    if count or not trajectory:
        return count
    for row in trajectory.get("commands") or []:
        if not isinstance(row, Mapping):
            continue
        blob = f"{row.get('tool') or ''} {row.get('args') or ''}"
        if pat.search(blob):
            count += 1
    return count


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


def resolve_log_facts(
    spec: JudgeSpec,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Answers for extras that are deterministic from the log. Empty → use the judge."""
    has_log = bool(spans) or bool(trajectory)
    if not has_log:
        return {}
    facts: dict[str, Any] = {}
    for question in spec.extras:
        computed = _compute_question(question, spans, trajectory=trajectory)
        if computed is not None:
            facts[question.id] = computed
    return facts


def apply_log_facts(
    spec: JudgeSpec,
    answers: Mapping[str, Any] | None,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Replace judge answers with log facts when the check can be computed."""
    merged = dict(answers or {})
    merged.update(resolve_log_facts(spec, spans, trajectory=trajectory))
    return merged


def _compute_question(
    question: JudgeQuestion,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if question.type != "predicate":
        return None
    ask = question.ask or ""
    tool = _primary_tool(ask, spans, trajectory=trajectory)
    if not tool:
        return None
    kind = _fact_kind(ask)
    if kind == "count":
        count = count_tool_calls(spans, tool, trajectory=trajectory)
        if count == 0:
            return None
        return _predicate(count <= 1, source="log")
    if kind == "called":
        count = count_tool_calls(spans, tool, trajectory=trajectory)
        called = count > 0
        if not called:
            return None
        never = bool(re.search(r"never called|did not call|didn't call", ask, re.IGNORECASE))
        if _ANSWER_NO_IF.search(ask) and not never:
            return _predicate(False, source="log")
        return _predicate(True, source="log")
    if kind == "return":
        results = tool_results(spans, tool, trajectory=trajectory)
        if not results:
            return None
        blob = " ".join(results).lower()
        wanted = _wanted_status(ask)
        if not wanted:
            return None
        present = any(token in blob for token in wanted)
        if re.search(r"\bnot\s+" + re.escape(wanted[0]), ask, re.IGNORECASE):
            present = not present if "not" in ask.lower() else present
        if _ANSWER_NO_IF.search(ask) and re.search(r"\bnot\b.{0,40}" + re.escape(wanted[0]), ask, re.IGNORECASE):
            return _predicate(any(token in blob for token in wanted), source="log")
        return _predicate(present, source="log")
    return None


def _predicate(yes: bool, *, source: str) -> dict[str, Any]:
    value = 1.0 if yes else 0.0
    return {"probability": value, "noul": value, "source": source}


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
        name
        for name in candidates
        if count_tool_calls(spans, name, trajectory=trajectory) > 0
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
    if _TOOL_CALLED.search(ask) or re.search(r"\b(?:was|were)\s+.{0,20}called\b", ask, re.IGNORECASE):
        return "called"
    return None


def _wanted_status(ask: str) -> list[str]:
    found = [match.group(1).lower() for match in _STATUS.finditer(ask)]
    mapped: list[str] = []
    for token in found:
        if token in {"success"}:
            mapped.append("succeeded")
        elif token in {"timed out"}:
            mapped.append("timeout")
        else:
            mapped.append(token)
    return mapped
