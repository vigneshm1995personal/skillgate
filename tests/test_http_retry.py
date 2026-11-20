from __future__ import annotations

import httpx
import pytest

from skillgate_ai.http_retry import (
    DEFAULT_ATTEMPTS,
    RetryableStatus,
    call_with_retry,
    is_retryable_status,
    parse_retry_after,
)


class _Resp:
    def __init__(
        self, status_code: int, headers: dict[str, str] | None = None, payload: object | None = None
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload if payload is not None else {}

    def json(self) -> object:
        return self._payload


def test_retries_on_429_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr("skillgate_ai.http_retry.sleep", delays.append)
    calls = {"n": 0}

    def once() -> _Resp:
        calls["n"] += 1
        if calls["n"] < 3:
            raise RetryableStatus(429, retry_after=None)
        return _Resp(200)

    result = call_with_retry(once)
    assert result.status_code == 200
    assert calls["n"] == 3
    assert delays


def test_retries_on_503_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.http_retry.sleep", lambda _s: None)
    calls = {"n": 0}

    def once() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RetryableStatus(503)
        return "ok"

    assert call_with_retry(once) == "ok"
    assert calls["n"] == 2


def test_retries_on_timeout_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.http_retry.sleep", lambda _s: None)
    calls = {"n": 0}

    def once() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("slow")
        return "ok"

    assert call_with_retry(once) == "ok"
    assert calls["n"] == 2


def test_does_not_retry_401() -> None:
    calls = {"n": 0}

    def once() -> _Resp:
        calls["n"] += 1
        return _Resp(401)

    result = call_with_retry(once)
    assert result.status_code == 401
    assert calls["n"] == 1


def test_does_not_retry_400_exception() -> None:
    calls = {"n": 0}

    def once() -> str:
        calls["n"] += 1
        raise ValueError("bad request")

    with pytest.raises(ValueError):
        call_with_retry(once)
    assert calls["n"] == 1


def test_respects_retry_after(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr("skillgate_ai.http_retry.sleep", delays.append)
    calls = {"n": 0}

    def once() -> str:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RetryableStatus(429, retry_after=7.0)
        return "ok"

    assert call_with_retry(once) == "ok"
    assert delays
    assert delays[0] == 7.0


def test_retry_after_capped_at_max_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    delays: list[float] = []
    monkeypatch.setattr("skillgate_ai.http_retry.sleep", delays.append)

    def once() -> str:
        raise RetryableStatus(503, retry_after=120.0)

    with pytest.raises(RetryableStatus):
        call_with_retry(once, attempts=2, max_wait_sec=30.0, deadline_sec=10_000)
    assert delays
    assert delays[0] == 30.0


def test_gives_up_after_attempt_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.http_retry.sleep", lambda _s: None)
    calls = {"n": 0}

    def once() -> str:
        calls["n"] += 1
        raise RetryableStatus(503)

    with pytest.raises(RetryableStatus):
        call_with_retry(once)
    assert calls["n"] == DEFAULT_ATTEMPTS


def test_retries_false_is_single_attempt() -> None:
    calls = {"n": 0}

    def once() -> str:
        calls["n"] += 1
        raise httpx.ConnectError("down")

    with pytest.raises(httpx.ConnectError):
        call_with_retry(once, retries=False)
    assert calls["n"] == 1


def test_is_retryable_status_skips_auth_and_quota() -> None:
    assert is_retryable_status(429) is True
    assert is_retryable_status(503) is True
    assert is_retryable_status(401) is False
    assert is_retryable_status(400) is False
    assert is_retryable_status(429, quota_exhausted=True) is False


def test_parse_retry_after_seconds() -> None:
    assert parse_retry_after({"Retry-After": "12"}) == 12.0
    assert parse_retry_after({"retry-after": "3.5"}) == 3.5
    assert parse_retry_after({}) is None
    assert parse_retry_after(None) is None


def test_retry_log_has_no_secrets(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("skillgate_ai.http_retry.sleep", lambda _s: None)

    def once() -> str:
        raise RetryableStatus(503)

    with (
        caplog.at_level("WARNING", logger="skillgate_ai.http_retry"),
        pytest.raises(RetryableStatus),
    ):
        call_with_retry(once, attempts=2)
    text = " ".join(caplog.messages)
    assert "retrying outbound request" in text
    assert "HTTP 503" in text
    assert "Authorization" not in text
    assert "sk-" not in text
    assert "Bearer" not in text
