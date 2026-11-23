from __future__ import annotations

import re

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
_RETURN = re.compile(r"\breturns?\b|\breturned\b|\bresult\b(?!s)", re.IGNORECASE)
_STATUS = re.compile(
    r"\b(succeeded|success|timeout|timed out|failed|502|error)\b",
    re.IGNORECASE,
)
_WORD = r"(?<![A-Za-z0-9_]){name}(?![A-Za-z0-9_])"
_INVOKE_TOOLS = frozenset({"shell", "bash", "command", "exec"})
_WRITE_PAYLOAD = re.compile(
    r'"(?:content|contents|body|text)"\s*:',
    re.IGNORECASE,
)
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


