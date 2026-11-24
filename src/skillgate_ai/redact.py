"""Redact secrets from harness CLI output before persistence or display."""

from __future__ import annotations

import re

_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE)
_BASIC = re.compile(r"\bBasic\s+[A-Za-z0-9+/=]{8,}\b", re.IGNORECASE)
_AUTH_HEADER = re.compile(r"(?i)\b(authorization|x-api-key|api-key|cookie)\s*:\s*[^\r\n]+")
_CRED_PAIR = re.compile(r"(?i)\b(password|passwd|token|secret|api[_-]?key)\s*[=:]\s*\S+")
_URL_USERINFO = re.compile(r"(?://)[^/\s:@]+:[^@\s/]+@")
_PREFIXED_KEY = re.compile(
    r"\b(?:sk|pk|rk|crsr|key|ghp|gho|ghu|ghs|ghr|github_pat|AKIA|ASIA|xox[baprs])"
    r"[-_][A-Za-z0-9._-]{8,}\b"
)


def _redact_prefixed_key(match: re.Match[str]) -> str:
    token = match.group(0)
    for sep in ("-", "_"):
        if sep in token:
            return f"{token.split(sep, 1)[0]}{sep}***"
    return "***"


_HIGH_ENTROPY = re.compile(r"\b[A-Za-z0-9+/=_-]{32,}\b")


def redact_harness_text(text: str, *, known: str | None = None) -> str:
    """Redact likely secrets. Order matters: specific patterns before generic entropy."""
    if not text:
        return text
    out = text
    if known and known.strip():
        out = out.replace(known.strip(), "***")
    out = _URL_USERINFO.sub("://***:***@", out)
    out = _AUTH_HEADER.sub(lambda m: f"{m.group(1)}: ***", out)
    out = _BEARER.sub("Bearer ***", out)
    out = _JWT.sub("eyJ***", out)
    out = _BASIC.sub("Basic ***", out)
    out = _CRED_PAIR.sub(lambda m: f"{m.group(1)}=***", out)
    out = _PREFIXED_KEY.sub(_redact_prefixed_key, out)
    out = _HIGH_ENTROPY.sub("***", out)
    return out


def tail_text(
    text: str,
    *,
    max_lines: int = 20,
    max_chars: int = 2400,
    known: str | None = None,
) -> str:
    lines = (text or "").splitlines()
    if len(lines) > max_lines:
        lines = lines[-max_lines:]
    blob = "\n".join(lines)
    if len(blob) > max_chars:
        blob = blob[-max_chars:]
    return redact_harness_text(blob, known=known)
