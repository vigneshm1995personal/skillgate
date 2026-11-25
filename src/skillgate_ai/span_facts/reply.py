from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from skillgate_ai.span_facts.asks import _predicate, _primary_tool
from skillgate_ai.span_facts.patterns import _REPLY, _STATUS
from skillgate_ai.span_facts.tools import tool_results

_ISSUED_RE = re.compile(
    r"\b(?:has been|have been|was|already|i(?:['’]ve| have)|we(?:['’]ve| have))\s+"
    r"(?:issued|processed|completed|submitted)\b|"
    r"money is already on its way|"
    r"(?:issued|processed|submitted)\s+a\s+(?:full\s+)?refund|"
    r"\bis on (?:its|the) way\b",
    re.IGNORECASE,
)
_HEDGE_RE = re.compile(
    r"has not gone through|have not gone through|hasn['’]t gone through|"
    r"haven['’]t gone through|not gone through|"
    r"did(?:n['’]t| not) go through|attempt did|"
    r"nothing has been returned|no funds have been returned|"
    r"have not been returned|has not been returned|"
    r"usd 0\.00 has been returned|usd 0\.00 refunded|"
    r"0\.00(?:\s+\w+){0,4}\s+so far|"
    r"under review|for review|is reviewing|reviewing that refund|"
    r"still pending|is pending\b|pending review|"
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


def _output_file(outputs: Sequence[Mapping[str, Any]] | str | None, name: str) -> str:
    if isinstance(outputs, str):
        return outputs if name in {"reply.txt", "calls.log"} else ""
    needle = name.lower()
    for item in outputs or []:
        if not isinstance(item, Mapping):
            continue
        path = str(item.get("path") or "").replace("\\", "/").lower()
        if path.endswith((needle, "/" + needle)):
            return str(item.get("content") or item.get("body") or item.get("extracted_text") or "")
    return ""


def _reply_text(outputs: Sequence[Mapping[str, Any]] | str | None) -> str:
    return _output_file(outputs, "reply.txt").strip()


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
    raw_err = resp.get("error")
    err: Mapping[str, Any] = raw_err if isinstance(raw_err, Mapping) else {}
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


def _count_from_calls_log(ask: str, outputs: Sequence[Mapping[str, Any]] | str | None) -> int:
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
                if (
                    isinstance(refund, Mapping)
                    and str(refund.get("status") or "").lower() == "succeeded"
                ):
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
        if outputs is None:
            return None
        if _ALREADY_ISSUED_ASK.search(ask) or _REPLY.search(ask):
            return _predicate(False, source="log", reason="reply.txt missing")
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
