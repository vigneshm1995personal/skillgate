"""OpenAI HTTP: retries, friendly errors, secret redaction. Never logs keys."""

from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Mapping

import httpx

from skillgate_ai.errors import OFFLINE_MESSAGE
from skillgate_ai.judge_bank import UNUSABLE_ANSWER

_LOG = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.openai.com/v1"
_TRANSIENT = frozenset({429, 502, 503, 504})
_QUOTA_CODES = frozenset({"insufficient_quota", "credit_balance_exhausted"})
_RETRY_BACKOFF_SEC = (0.5, 1.0, 2.0)
_MAX_ATTEMPTS = 3
_SK_TOKEN = re.compile(r"sk-[A-Za-z0-9_*\-]{2,}")
OUT_OF_CREDITS = (
    "Your OpenAI account is out of credits. Add credits at platform.openai.com "
    "billing, then try again."
)

PostFn = Callable[..., httpx.Response]


def redact_secrets(text: str, secret: str | None = None) -> str:
    """Strip the configured key and any sk-… token (full or masked) from text."""
    if not text:
        return text
    out = text
    if secret:
        out = out.replace(secret, "***")
    return _SK_TOKEN.sub("sk-***", out)


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
    if status == 404:
        return f"{label} has no scoring endpoint for this key."
    if status in {402, 429} and error_code in _QUOTA_CODES:
        if who == "OpenAI":
            return OUT_OF_CREDITS
        return f"{label} is out of credits. Add credits, then try again."
    if status == 402:
        return f"{label} is out of credits. Add credits, then try again."
    if status == 429:
        return f"{label} rate-limited this request. Wait and retry, or check billing."
    if status == 400:
        return f"{label} rejected this scoring request."
    return f"{label} couldn't score this check (HTTP {status})."


def _status_error(
    response: httpx.Response,
    *,
    model: str,
    who: str = "the judge",
) -> dict[str, Any]:
    code = openai_error_code(response)
    reason = user_message_for_status(response.status_code, error_code=code, who=who)
    _LOG.warning("scoring HTTP %s", response.status_code)
    return {
        "status": "error",
        "reason": reason,
        "model": model,
        "http_status": response.status_code,
    }


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
                "OpenAI scoring transport error (attempt %s/%s): %s",
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
                "OpenAI scoring HTTP %s (attempt %s/%s)",
                response.status_code,
                attempt + 1,
                attempts,
            )
            time.sleep(_RETRY_BACKOFF_SEC[min(attempt, len(_RETRY_BACKOFF_SEC) - 1)])
            continue
        return response
    assert last_exc is not None
    raise last_exc


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
        return _status_error(response, model=model, who=who)
    try:
        data = response.json()
    except ValueError:
        return {"status": "error", "reason": UNUSABLE_ANSWER, "model": model}
    if not isinstance(data, Mapping):
        return {"status": "error", "reason": UNUSABLE_ANSWER, "model": model}
    return {"status": "ok", "data": data}
