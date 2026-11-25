from __future__ import annotations

import httpx
import pytest

from skillgate_ai.errors import SkillGateError
from skillgate_ai.openai_http import (
    _CHAT_JUDGE_URLS,
    openai_error_message,
    redact_secrets,
    refuse_chat_judge_url,
    sanitize_upstream,
)


def test_redact_secrets_masks_configured_key_and_sk_tokens() -> None:
    out = redact_secrets("key=abc123 sk-proj-XYZ", "abc123")
    assert "***" in out
    assert "sk-***" in out
    assert "abc123" not in out
    assert "XYZ" not in out
    assert redact_secrets("") == ""


def test_sanitize_upstream_collapses_whitespace_and_trims() -> None:
    assert sanitize_upstream("  bad   request .  ") == "bad request"


@pytest.mark.parametrize("fragment", _CHAT_JUDGE_URLS)
def test_refuse_chat_judge_url_raises_exit_2(fragment: str) -> None:
    with pytest.raises(SkillGateError) as caught:
        refuse_chat_judge_url(f"https://x.example{fragment}")
    assert caught.value.exit_code == 2


def test_refuse_chat_judge_url_allows_decisions() -> None:
    assert refuse_chat_judge_url("https://x.example/v1/decisions") is None


def test_openai_error_message_non_json_returns_none() -> None:
    response = httpx.Response(500, content=b"not json")
    assert openai_error_message(response) is None
