"""Shared exponential backoff for outbound HTTP.

Retries timeouts, network errors, HTTP 429, and 5xx. Never retries 4xx
auth/validation. Logs attempt counts only — no URLs, headers, or secrets.
"""

from __future__ import annotations

import http.client
import logging
import os
import socket
import ssl
import urllib.error
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TypeVar

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception,
    stop_after_attempt,
    stop_before_delay,
    wait_random_exponential,
)

DEFAULT_ATTEMPTS = 5
DEFAULT_MAX_WAIT_SEC = 30.0
DEFAULT_DEADLINE_SEC = 60.0
TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})

_LOG = logging.getLogger(__name__)
T = TypeVar("T")


def sleep(seconds: float) -> None:
    """Wait hook tests patch. Tenacity calls this instead of time.sleep."""
    import time

    time.sleep(seconds)


class RetryableStatus(Exception):
    """HTTP 429/5xx that should be retried. Holds the last response when present."""

    def __init__(
        self,
        status: int,
        retry_after: float | None = None,
        response: object | None = None,
    ) -> None:
        self.status = status
        self.retry_after = retry_after
        self.response = response
        super().__init__(f"HTTP {status}")


class RetryBudgetExceeded(RetryableStatus):
    """Retry-After or backoff would exceed the total retry deadline."""


def retry_attempts() -> int:
    return _env_int("SKILLGATE_HTTP_RETRY_ATTEMPTS", DEFAULT_ATTEMPTS)


def retry_max_wait() -> float:
    return _env_float("SKILLGATE_HTTP_RETRY_MAX_WAIT", DEFAULT_MAX_WAIT_SEC)


def retry_deadline() -> float:
    return _env_float("SKILLGATE_HTTP_RETRY_DEADLINE", DEFAULT_DEADLINE_SEC)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def is_retryable_status(status: int, *, quota_exhausted: bool = False) -> bool:
    if quota_exhausted:
        return False
    return status in TRANSIENT_STATUS


def parse_retry_after(headers: Mapping[str, str] | None) -> float | None:
    if not headers:
        return None
    raw = None
    for key, value in headers.items():
        if key.lower() == "retry-after":
            raw = str(value).strip()
            break
    if not raw:
        return None
    try:
        return max(float(raw), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delay = (when - datetime.now(UTC)).total_seconds()
    return max(delay, 0.0)


def retry_after_from_response(response: object) -> float | None:
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        return parse_retry_after(headers)
    except (TypeError, AttributeError):
        getter = getattr(headers, "get", None)
        if callable(getter):
            raw = getter("Retry-After") or getter("retry-after")
            return parse_retry_after({"Retry-After": str(raw)} if raw is not None else {})
        return None


def is_retryable_exception(exc: BaseException) -> bool:
    if isinstance(exc, RetryBudgetExceeded):
        return False
    if isinstance(exc, RetryableStatus):
        return True
    if isinstance(exc, httpx.TimeoutException):
        return True
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ReadError,
            httpx.WriteError,
            httpx.RemoteProtocolError,
            httpx.PoolTimeout,
        ),
    ):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return False
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        if isinstance(reason, ssl.SSLCertVerificationError):
            return False
        if isinstance(reason, socket.gaierror):
            return reason.errno == socket.EAI_AGAIN
        return isinstance(reason, (TimeoutError, ConnectionError, OSError))
    return isinstance(exc, http.client.HTTPException)


class _WaitRetryOrExponential:
    def __init__(self, max_wait: float, deadline_sec: float) -> None:
        self._max = max_wait
        self._deadline = deadline_sec
        self._exp = wait_random_exponential(multiplier=0.5, max=max_wait)

    def __call__(self, retry_state: RetryCallState) -> float:
        elapsed = retry_state.seconds_since_start if retry_state.seconds_since_start else 0.0
        remaining = self._deadline - elapsed
        if remaining <= 0:
            raise RetryBudgetExceeded(0, retry_after=None)
        exc = retry_state.outcome.exception() if retry_state.outcome else None
        if isinstance(exc, RetryableStatus) and exc.retry_after is not None:
            delay = max(exc.retry_after, 0.0)
            if delay > remaining:
                raise RetryBudgetExceeded(exc.status, retry_after=delay)
            return delay
        return min(float(self._exp(retry_state)), self._max, remaining)


def _log_retry(retry_state: RetryCallState) -> None:
    exc = retry_state.outcome.exception() if retry_state.outcome else None
    if isinstance(exc, RetryableStatus):
        reason = f"HTTP {exc.status}"
    elif exc is not None:
        reason = type(exc).__name__
    else:
        reason = "transient error"
    _LOG.warning(
        "retrying outbound request (%s): %s",
        retry_state.attempt_number,
        reason,
    )


def call_with_retry(
    fn: Callable[[], T],
    *,
    retries: bool = True,
    attempts: int | None = None,
    max_wait_sec: float | None = None,
    deadline_sec: float | None = None,
) -> T:
    """Run ``fn`` with exponential backoff. ``retries=False`` is a single attempt."""
    if not retries:
        return fn()
    n = attempts if attempts is not None else retry_attempts()
    max_wait = max_wait_sec if max_wait_sec is not None else retry_max_wait()
    deadline = deadline_sec if deadline_sec is not None else retry_deadline()
    retrying = Retrying(
        stop=stop_after_attempt(n) | stop_before_delay(deadline),
        wait=_WaitRetryOrExponential(float(max_wait), float(deadline)),
        retry=retry_if_exception(is_retryable_exception),
        sleep=sleep,
        reraise=True,
        before_sleep=_log_retry,
    )
    return retrying(fn)
