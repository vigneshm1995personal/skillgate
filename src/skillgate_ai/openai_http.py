"""OpenAI HTTP: retries, friendly errors, secret redaction. Never logs keys."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Mapping

import httpx

from skillgate_ai.errors import OFFLINE_MESSAGE, SkillGateError
from skillgate_ai.judge_bank import UNUSABLE_ANSWER

_LOG = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
_TRANSIENT = frozenset({429, 500, 502, 503, 504})
_QUOTA_CODES = frozenset({"insufficient_quota", "credit_balance_exhausted"})
_RETRY_BACKOFF_SEC = (0.5, 1.0, 2.0)
_MAX_ATTEMPTS = 3
_SK_TOKEN = re.compile(r"sk-[A-Za-z0-9_*\-]{2,}")
_PROVIDER_NOISE = re.compile(
    r"\b(openrouter(?:\.ai)?|typesafe(?:-ai)?|jev(?:ex)?|openai|cloudflare|"
    r"anthropic|aws|workers ai)\b[:\s]*",
    re.I,
)
OUT_OF_CREDITS = "This account is out of credits. Add credits, then try again."

PostFn = Callable[..., httpx.Response]


def redact_secrets(text: str, secret: str | None = None) -> str:
    """Strip the configured key and any sk-… token (full or masked) from text."""
    if not text:
        return text
    out = text
    if secret:
        out = out.replace(secret, "***")
    return _SK_TOKEN.sub("sk-***", out)


def sanitize_upstream(text: str, secret: str | None = None) -> str:
    """Keep the upstream reason. Never print keys or scoring-provider names."""
    out = redact_secrets((text or "").strip(), secret)
    out = _PROVIDER_NOISE.sub("", out)
    return re.sub(r"\s+", " ", out).strip(" :.-")


def openai_error_message(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    return _mapping_error_message(data)


def _mapping_error_message(data: Any) -> str | None:
    if not isinstance(data, Mapping):
        return None
    err = data.get("error")
    if isinstance(err, str) and err.strip():
        return err.strip()
    if not isinstance(err, Mapping):
        return None
    for key in ("message", "msg"):
        value = err.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _mapping_error_status(data: Any) -> int | None:
    if not isinstance(data, Mapping):
        return None
    err = data.get("error")
    if not isinstance(err, Mapping):
        return None
    for key in ("code", "status"):
        value = err.get(key)
        if isinstance(value, int) and value >= 400:
            return value
        if isinstance(value, str) and value.isdigit():
            parsed = int(value)
            if parsed >= 400:
                return parsed
    return None


def _payload_has_answers(data: Mapping[str, Any]) -> bool:
    rows = data.get("answers")
    if isinstance(rows, Mapping):
        return bool(rows)
    return isinstance(rows, list) and bool(rows)


def openai_error_code(response: httpx.Response) -> str | None:
    try:
        data = response.json()
    except ValueError:
        return None
    if not isinstance(data, Mapping):
        return None
    err = data.get("error")
    if not isinstance(err, Mapping):
        return None
    for key in ("code", "type"):
        value = err.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def is_quota_exhausted(response: httpx.Response) -> bool:
    return response.status_code == 429 and openai_error_code(response) in _QUOTA_CODES


def user_message_for_status(
    status: int,
    *,
    error_code: str | None = None,
    who: str = "the judge",
) -> str:
    label = "The judge" if who == "the judge" else who
    if status == 401:
        return f"{label} did not accept this API key."
    if status == 403:
        return f"{label} scoring is not enabled for this key."
    if status in {404, 405}:
        from skillgate_ai.judge_setup import WRONG_ENDPOINT

        return WRONG_ENDPOINT
    if status in {402, 429} and error_code in _QUOTA_CODES:
        if who == "OpenAI":
            return OUT_OF_CREDITS
        return OUT_OF_CREDITS if label == "The judge" else f"{label} is out of credits. Add credits, then try again."
    if status == 402:
        return f"{label} is out of credits. Add credits, then try again."
    if status == 429:
        return f"{label} rate-limited this request. Wait and retry, or check billing."
    if status == 400:
        return f"{label} rejected this scoring request."
    if status in {500, 502, 503, 504}:
        return f"{label} couldn't score this check. Retry — this is often temporary."
    return f"{label} couldn't score this check."


def _status_error(
    response: httpx.Response,
    *,
    model: str,
    who: str = "the judge",
    secret: str | None = None,
) -> dict[str, Any]:
    code = openai_error_code(response)
    reason = user_message_for_status(response.status_code, error_code=code, who=who)
    if response.status_code == 404:
        _LOG.debug("scoring request failed")
    else:
        _LOG.warning("scoring request failed")
    out: dict[str, Any] = {
        "status": "error",
        "reason": reason,
        "model": model,
        "http_status": response.status_code,
    }
    upstream = sanitize_upstream(openai_error_message(response) or "", secret)
    if upstream:
        out["upstream"] = upstream
    return out


def post_openai(
    url: str,
    *,
    headers: dict[str, str],
    payload: dict[str, Any],
    timeout_sec: float,
    post: PostFn | None = None,
    retries: bool = True,
) -> httpx.Response:
    sender = post or httpx.post
    attempts = _MAX_ATTEMPTS if retries else 1
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            response = sender(url, headers=headers, json=payload, timeout=timeout_sec)
        except httpx.TimeoutException:
            raise
        except httpx.HTTPError as exc:
            last_exc = exc
            if attempt >= attempts - 1:
                raise
            _LOG.warning(
                "scoring transport error (attempt %s/%s): %s",
                attempt + 1,
                attempts,
                type(exc).__name__,
            )
            time.sleep(_RETRY_BACKOFF_SEC[min(attempt, len(_RETRY_BACKOFF_SEC) - 1)])
            continue
        if (
            response.status_code in _TRANSIENT
            and attempt < attempts - 1
            and not is_quota_exhausted(response)
        ):
            _LOG.warning(
                "scoring request failed (attempt %s/%s)",
                attempt + 1,
                attempts,
            )
            time.sleep(_RETRY_BACKOFF_SEC[min(attempt, len(_RETRY_BACKOFF_SEC) - 1)])
            continue
        return response
    assert last_exc is not None
    raise last_exc


_CHAT_JUDGE_URLS = ("/responses", "/chat/completions", "/v1/chat")


def refuse_chat_judge_url(url: str) -> None:
    """Scoring posts go to a decision endpoint. Chat and Responses URLs fail closed."""
    for fragment in _CHAT_JUDGE_URLS:
        if fragment in url:
            raise SkillGateError(
                "Scoring uses a decision model. Chat and Responses scoring was removed.",
                exit_code=2,
            )


def post_openai_json(
    url: str,
    *,
    api_key: str,
    payload: dict[str, Any],
    timeout_sec: float,
    model: str,
    post: PostFn | None = None,
    retries: bool = True,
    who: str = "the judge",
) -> dict[str, Any]:
    """POST JSON. Transport/HTTP/parse failures return ``status=error``."""
    refuse_chat_judge_url(url)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    label = "The judge" if who == "the judge" else who
    try:
        response = post_openai(
            url,
            headers=headers,
            payload=payload,
            timeout_sec=timeout_sec,
            post=post,
            retries=retries,
        )
    except httpx.TimeoutException:
        return {"status": "error", "reason": f"{label} scoring timed out.", "model": model}
    except httpx.HTTPError:
        return {"status": "error", "reason": OFFLINE_MESSAGE, "model": model}
    if response.status_code >= 400:
        return _status_error(response, model=model, who=who, secret=api_key)
    try:
        data = response.json()
    except ValueError:
        return {"status": "error", "reason": UNUSABLE_ANSWER, "model": model}
    if isinstance(data, list):
        data = {"answers": data}
    if not isinstance(data, Mapping):
        return {"status": "error", "reason": UNUSABLE_ANSWER, "model": model}
    if _mapping_error_message(data) and not _payload_has_answers(data):
        status = _mapping_error_status(data) or 400
        reason = user_message_for_status(status, who=who)
        upstream = sanitize_upstream(_mapping_error_message(data) or "", api_key)
        out: dict[str, Any] = {
            "status": "error",
            "reason": reason,
            "model": model,
            "http_status": status,
        }
        if upstream:
            out["upstream"] = upstream
        return out
    return {"status": "ok", "data": data}
