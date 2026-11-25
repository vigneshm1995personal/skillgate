from __future__ import annotations

import httpx

from skillgate_ai.openai_http import (
    _status_error,
    is_quota_exhausted,
    openai_error_code,
    openai_error_message,
    redact_secrets,
    sanitize_upstream,
    user_message_for_status,
)


def test_redact_secrets_strips_configured_and_sk_tokens() -> None:
    text = "failed with sk-live-token and sk-abc123"
    out = redact_secrets(text, secret="sk-live-token")
    assert "sk-live-token" not in out
    assert "sk-***" in out


def test_sanitize_upstream_strips_provider_noise() -> None:
    assert "bad key" in sanitize_upstream("OpenAI: bad key").lower()


def test_openai_error_message_reads_nested_json() -> None:
    response = httpx.Response(
        400,
        json={"error": {"message": "invalid", "code": "bad"}},
    )
    assert openai_error_message(response) == "invalid"
    empty = httpx.Response(500, content=b"not json")
    assert openai_error_message(empty) is None


def test_user_message_for_status_branches() -> None:
    assert "API key" in user_message_for_status(401)
    assert "rate-limit" in user_message_for_status(429).lower()
    assert "credits" in user_message_for_status(402, who="OpenAI")


def test_is_quota_exhausted_reads_error_code() -> None:
    response = httpx.Response(
        429,
        json={"error": {"code": "insufficient_quota", "message": "x"}},
    )
    assert is_quota_exhausted(response) is True
    assert openai_error_code(response) == "insufficient_quota"


def test_status_error_payload_sanitizes_upstream() -> None:
    response = httpx.Response(400, json={"error": {"message": "sk-secret123 bad"}})
    payload = _status_error(response, model="gpt-test", secret="sk-secret123")
    assert payload["status"] == "error"
    assert "sk-secret123" not in (payload.get("upstream") or "")
