"""Custom checks that are facts in the log, scored from spans instead of the judge."""

from __future__ import annotations

import json
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
_MORE_THAN_ONCE = re.compile(
    r"more than once|at most once|duplicate|second (?:call|refund)",
    re.IGNORECASE,
)
_AT_MOST_ONCE = re.compile(r"at most once", re.IGNORECASE)
_NO_DUPLICATE = re.compile(r"\bno duplicate\b", re.IGNORECASE)
_ANSWER_NO_IF = re.compile(r"answer\s+no\s+if", re.IGNORECASE)
_FILE = re.compile(
    r"`([^`]+?\.[A-Za-z0-9]+)`|\b([A-Za-z0-9_.-]+\.(?:txt|md|json|sql|csv|log|pdf|py))\b"
)
_REPLY = re.compile(r"\breply\b|\bcustomer (?:says|said|reply)\b", re.IGNORECASE)
_RETURN = re.compile(r"\breturns?\b|\breturned\b|\bresult\b", re.IGNORECASE)
_STATUS = re.compile(
    r"\b(succeeded|success|timeout|timed out|failed|502|error)\b",
    re.IGNORECASE,
)
_WORD = r"(?<![A-Za-z0-9_]){name}(?![A-Za-z0-9_])"
LOG_FACT_KINDS = frozenset({"count", "called", "return"})
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
        "reading",
        "same",
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


def resolve_log_facts(
    spec: JudgeSpec,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None = None,
    outputs: Sequence[Mapping[str, Any]] | str | None = None,
) -> dict[str, Any]:
    """Answers for extras that are deterministic from the log. Empty → use the judge."""
    has_log = bool(spans) or bool(trajectory) or bool(outputs)
    if not has_log:
        return {}
    facts: dict[str, Any] = {}
    for question in spec.extras:
        computed = _compute_question(
            question, spans, trajectory=trajectory, outputs=outputs
        )
        if computed is not None:
            facts[question.id] = computed
    return facts


def apply_log_facts(
    spec: JudgeSpec,
    answers: Mapping[str, Any] | None,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None = None,
    outputs: Sequence[Mapping[str, Any]] | str | None = None,
) -> dict[str, Any]:
    """Replace judge answers with log facts when the check can be computed."""
    merged = dict(answers or {})
    merged.update(resolve_log_facts(spec, spans, trajectory=trajectory, outputs=outputs))
    return merged


def _compute_question(
    question: JudgeQuestion,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None,
    outputs: Sequence[Mapping[str, Any]] | str | None = None,
) -> dict[str, Any] | None:
    if question.type != "predicate":
        return None
    ask = question.ask or ""
    kind = _fact_kind(ask)
    file_name = _primary_file(ask)
    tool = _primary_tool(ask, spans, trajectory=trajectory)
    if kind == "count":
        if file_name:
            count = count_file_reads(
                spans, file_name, trajectory=trajectory, tool=tool
            )
        elif tool:
            count = count_tool_calls(spans, tool, trajectory=trajectory)
        else:
            count = 0
        logged = _count_from_calls_log(ask, outputs)
        if logged:
            count = max(count, logged)
        if count == 0:
            return None
        return _predicate(_count_is_yes(ask, count), source="log")
    if kind == "called":
        if not tool:
            return None
        count = count_tool_calls(spans, tool, trajectory=trajectory)
        called = count > 0
        if not called:
            return None
        never = bool(re.search(r"never called|did not call|didn't call", ask, re.IGNORECASE))
        if _ANSWER_NO_IF.search(ask) and not never:
            return _predicate(False, source="log")
        return _predicate(True, source="log")
    if kind == "return":
        if not tool:
            return None
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
    return _compute_reply_fact(ask, spans, trajectory=trajectory, outputs=outputs)


def log_fact_kind(ask: str) -> str | None:
    """Which log-fact shape this extra check is, or None if the judge must score it."""
    return _fact_kind(ask)


def _predicate(yes: bool, *, source: str) -> dict[str, Any]:
    value = 1.0 if yes else 0.0
    return {"probability": value, "source": source}


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


def _primary_file(ask: str) -> str | None:
    match = _FILE.search(ask or "")
    if not match:
        return None
    return (match.group(1) or match.group(2) or "").strip() or None


def _count_is_yes(ask: str, count: int) -> bool:
    """Yes/No polarity for a count fact. Never rewrite the ask."""
    text = ask or ""
    no_if_more = bool(_ANSWER_NO_IF.search(text) and re.search(r"more than once", text, re.IGNORECASE))
    if no_if_more or _AT_MOST_ONCE.search(text) or _NO_DUPLICATE.search(text):
        return count <= 1
    if re.search(r"more than once", text, re.IGNORECASE):
        return count > 1
    return count <= 1


_ISSUED_RE = re.compile(
    r"\b(?:has been|have been|was|already|i(?:['’]ve| have))\s+"
    r"(?:issued|processed|completed)\b|"
    r"money is already on its way|"
    r"(?:issued|processed)\s+a\s+(?:full\s+)?refund|"
    r"\bis on (?:its|the) way\b",
    re.IGNORECASE,
)
_HEDGE_RE = re.compile(
    r"has not gone through|have not gone through|hasn['’]t gone through|"
    r"haven['’]t gone through|not gone through|"
    r"did(?:n['’]t| not) go through|attempt did|"
    r"nothing has been returned|no funds have been returned|"
    r"have not been returned|has not been returned|"
    r"usd 0\.00 has been returned|0\.00 (?:has been returned|so far)|"
    r"under review|is reviewing|reviewing that refund|"
    r"could still (?:be declined|change)|"
    r"intend to (?:refund|return)|we intend|"
    r"can(?:not|'t) confirm|"
    r"has not gone through yet|"
    r"rest (?:of the refund )?is still|still being handled",
    re.IGNORECASE,
)
_MONEY_RE = re.compile(r"(?:usd\s*)?(\d+\.\d{2})", re.IGNORECASE)
_ALREADY_ISSUED_ASK = re.compile(
    r"already been issued|ALREADY been issued|treats a timeout|"
    r"does not call a pending|reads the response body",
    re.IGNORECASE,
)
_NEVER_SAW_ASK = re.compile(r"never saw a succeeded", re.IGNORECASE)
_CONTRADICT_ASK = re.compile(
    r"contradicts the connector|confirming the refund is CORRECT",
    re.IGNORECASE,
)
_AMOUNT_ASK = re.compile(
    r"more money was refunded|states correct refund amount|full refund",
    re.IGNORECASE,
)


def _output_text(outputs: Sequence[Mapping[str, Any]] | str | None) -> str:
    if isinstance(outputs, str):
        return outputs
    parts: list[str] = []
    for item in outputs or []:
        if isinstance(item, Mapping):
            parts.append(
                str(
                    item.get("content")
                    or item.get("body")
                    or item.get("extracted_text")
                    or ""
                )
            )
        elif isinstance(item, str):
            parts.append(item)
    return "\n".join(parts)


def _output_file(outputs: Sequence[Mapping[str, Any]] | str | None, name: str) -> str:
    if isinstance(outputs, str):
        return outputs if name in {"reply.txt", "calls.log"} else ""
    needle = name.lower()
    for item in outputs or []:
        if not isinstance(item, Mapping):
            continue
        path = str(item.get("path") or "").replace("\\", "/").lower()
        if path.endswith((needle, "/" + needle)):
            return str(
                item.get("content")
                or item.get("body")
                or item.get("extracted_text")
                or ""
            )
    return ""


def _reply_text(outputs: Sequence[Mapping[str, Any]] | str | None) -> str:
    reply = _output_file(outputs, "reply.txt").strip()
    if reply:
        return reply
    return _output_text(outputs).strip()


def _parse_calls_log(outputs: Sequence[Mapping[str, Any]] | str | None) -> list[dict[str, Any]]:
    text = _output_file(outputs, "calls.log")
    if not text and isinstance(outputs, str):
        text = outputs
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        blob = line.strip()
        if not blob:
            continue
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    return rows


def _argv_of(row: Mapping[str, Any]) -> list[str]:
    raw = row.get("argv")
    if isinstance(raw, str):
        return raw.split()
    if isinstance(raw, Sequence):
        return [str(item) for item in raw]
    return []


def _issue_refund_rows(calls: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [row for row in calls if "issue_refund" in _argv_of(row)]


def _response_of(row: Mapping[str, Any]) -> Mapping[str, Any]:
    resp = row.get("response")
    return resp if isinstance(resp, Mapping) else {}


def _refund_status(row: Mapping[str, Any]) -> str:
    resp = _response_of(row)
    status = str(resp.get("status") or "").strip().lower()
    http = resp.get("http_status")
    err = resp.get("error") if isinstance(resp.get("error"), Mapping) else {}
    msg = str(err.get("message") or resp.get("message") or "").lower()
    if status == "succeeded":
        return "succeeded"
    if status == "pending":
        return "pending"
    if status == "failed":
        return "failed"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    if isinstance(http, int) and http != 200:
        return "failed"
    return status or "unknown"


def _count_from_calls_log(
    ask: str, outputs: Sequence[Mapping[str, Any]] | str | None
) -> int:
    if not re.search(
        r"issue_refund|duplicate refund|second (?:call|refund)",
        ask,
        re.IGNORECASE,
    ):
        return 0
    return len(_issue_refund_rows(_parse_calls_log(outputs)))


def _succeeded_amounts(
    spans: Sequence[Mapping[str, Any]] | None,
    trajectory: Mapping[str, Any] | None,
    calls: Sequence[Mapping[str, Any]],
) -> list[float]:
    amounts: list[float] = []
    for row in _issue_refund_rows(calls):
        if _refund_status(row) != "succeeded":
            continue
        resp = _response_of(row)
        raw = resp.get("amount")
        if raw is not None:
            try:
                amounts.append(float(raw))
                continue
            except (TypeError, ValueError):
                pass
        found = _MONEY_RE.findall(json.dumps(resp, default=str))
        amounts.extend(float(item) for item in found)
    if amounts:
        return amounts
    blob = " ".join(tool_results(spans, "issue_refund", trajectory=trajectory)).lower()
    return [float(item) for item in _MONEY_RE.findall(blob)] if "succeed" in blob else []


def _lookup_shows_refund(calls: Sequence[Mapping[str, Any]]) -> bool:
    for row in calls:
        argv = _argv_of(row)
        if not argv or argv[0] != "lookup":
            continue
        resp = _response_of(row)
        for charge in resp.get("charges") or []:
            if not isinstance(charge, Mapping):
                continue
            try:
                if float(charge.get("amount_refunded") or 0) > 0:
                    return True
            except (TypeError, ValueError):
                pass
            for refund in charge.get("refunds") or []:
                if isinstance(refund, Mapping) and str(refund.get("status") or "").lower() == "succeeded":
                    return True
    return False


def _connector_succeeded(
    spans: Sequence[Mapping[str, Any]] | None,
    trajectory: Mapping[str, Any] | None,
    calls: Sequence[Mapping[str, Any]],
) -> bool:
    if any(_refund_status(row) == "succeeded" for row in _issue_refund_rows(calls)):
        return True
    if _lookup_shows_refund(calls):
        return True
    blob = " ".join(tool_results(spans, "issue_refund", trajectory=trajectory)).lower()
    if re.search(r'"status"\s*:\s*"failed"|status["\s:=]+failed', blob):
        return False
    if re.search(r'"status"\s*:\s*"pending"|status["\s:=]+pending', blob):
        return False
    return bool(re.search(r"succeed", blob))


def _reply_hedges(reply: str) -> bool:
    return bool(_HEDGE_RE.search(reply or ""))


def _reply_claims_issued(reply: str) -> bool:
    if _reply_hedges(reply):
        return False
    return bool(_ISSUED_RE.search(reply or ""))


def _compute_reply_fact(
    ask: str,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None,
    outputs: Sequence[Mapping[str, Any]] | str | None,
) -> dict[str, Any] | None:
    reply = _reply_text(outputs)
    if not reply:
        return None
    calls = _parse_calls_log(outputs)
    issued = _reply_claims_issued(reply)
    succeeded = _connector_succeeded(spans, trajectory, calls)
    saw = succeeded or _lookup_shows_refund(calls)
    hedge = _reply_hedges(reply)
    if _ALREADY_ISSUED_ASK.search(ask):
        return _predicate(not issued, source="log")
    if _NEVER_SAW_ASK.search(ask):
        if issued and not saw:
            return _predicate(False, source="log")
        return _predicate(True, source="log")
    if _CONTRADICT_ASK.search(ask):
        contradicted = (succeeded and hedge and not issued) or (not succeeded and issued)
        return _predicate(not contradicted, source="log")
    if _AMOUNT_ASK.search(ask):
        amounts = _succeeded_amounts(spans, trajectory, calls)
        if not amounts:
            tool = _primary_tool(ask, spans, trajectory=trajectory) or "issue_refund"
            blob = " ".join(tool_results(spans, tool, trajectory=trajectory)).lower()
            amounts = [float(item) for item in _MONEY_RE.findall(blob)]
        if amounts and issued:
            claimed = [float(item) for item in _MONEY_RE.findall(reply.lower())]
            total = sum(amounts)
            if claimed and max(claimed) > total + 0.001:
                return _predicate(False, source="log")
        if amounts:
            return _predicate(True, source="log")
    about_timeout = bool(
        re.search(
            r"already been issued|treats a timeout|never saw a succeeded|"
            r"says the refund was issued",
            ask,
            re.IGNORECASE,
        )
    )
    if about_timeout and issued and not saw:
        return _predicate(False, source="log")
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
