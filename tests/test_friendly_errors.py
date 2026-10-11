from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from skillgate_ai.case_pack import CasePack
from skillgate_ai.config import LLMConfig
from skillgate_ai.errors import (
    BAD_OPENAI_KEY_MESSAGE,
    OFFLINE_MESSAGE,
    friendly_validation_error,
)
from skillgate_ai.harness import LLMHarness
from skillgate_ai.sandbox import LocalSandbox


def _cfg(**overrides: object) -> LLMConfig:
    fields: dict[str, object] = {
        "cursor_api_key": None,
        "gateway_api_key": None,
        "gateway_base_url": "https://api.openai.com/v1",
        "gateway_model": "openai/gpt-4o-mini",
        "anthropic_api_key": None,
        "anthropic_model": "claude-sonnet-4-20250514",
        "cursor_agent_bin": "agent",
        "codex_api_key": None,
        "codex_bin": "codex",
        "codex_reasoning_effort": "medium",
        "codex_model": None,
        "harness_pref": "auto",
        "sandbox_pref": "local",
        "docker_image": "skillgate-sandbox:v0",
        "temperature": 0.0,
        "openai_api_key": "sk-invalid-fake",
    }
    fields.update(overrides)
    return LLMConfig(**fields)  # type: ignore[arg-type]


def test_dns_failure_is_offline_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    exc = httpx.ConnectError("[Errno -3] Temporary failure in name resolution")

    def fake_post(*_args, **_kwargs):
        raise exc

    monkeypatch.setattr("skillgate_ai.harness.httpx.post", fake_post)
    sandbox = LocalSandbox(tmp_path)
    try:
        from skillgate_ai.errors import HarnessError

        with pytest.raises(HarnessError) as caught:
            LLMHarness(_cfg()).run(sandbox, "hello", [], timeout_sec=5)
    finally:
        sandbox.close()
    assert "Errno" in str(exc)
    assert caught.value.message == OFFLINE_MESSAGE
    assert "Errno" not in caught.value.message
    assert "BYO" not in caught.value.message


def test_schema_validation_names_schema_not_pydantic() -> None:
    raw = {"schema": 2, "skill": "pdf", "cases": []}
    with pytest.raises(ValidationError) as caught:
        CasePack.model_validate(raw)
    text = friendly_validation_error(caught.value, kind="Case pack", raw=raw)
    assert "pydantic" not in text.lower()
    assert "errors.pydantic.dev" not in text
    assert "schema" in text.lower()


def test_case_id_validation_names_the_id() -> None:
    raw = {
        "schema": 1,
        "skill": "pdf",
        "cases": [
            {
                "id": "Bad_ID",
                "status": "pinned",
                "prompt": "p",
                "should_trigger": True,
            }
        ],
    }
    with pytest.raises(ValidationError) as caught:
        CasePack.model_validate(raw)
    text = friendly_validation_error(caught.value, kind="Case pack", raw=raw)
    assert "Bad_ID" in text
    assert "cases.0.id" not in text
    assert "pydantic" not in text.lower()


def test_gateway_401_is_bad_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    class FakeResponse:
        status_code = 401

        def json(self):
            return {"error": {"message": "Incorrect API key"}}

    def fake_post(*_args, **_kwargs):
        return FakeResponse()

    monkeypatch.setattr("skillgate_ai.harness.httpx.post", fake_post)
    sandbox = LocalSandbox(tmp_path)
    try:
        with pytest.raises(Exception) as caught:
            LLMHarness(_cfg()).run(sandbox, "hello", [], timeout_sec=5)
    finally:
        sandbox.close()
    from skillgate_ai.errors import HarnessError

    assert isinstance(caught.value, HarnessError)
    assert caught.value.message == BAD_OPENAI_KEY_MESSAGE
    assert "BYO" not in caught.value.message
    assert "401" not in caught.value.message


def test_gateway_offline_is_friendly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def fake_post(*_args, **_kwargs):
        raise httpx.ConnectError("[Errno -3] Temporary failure in name resolution")

    monkeypatch.setattr("skillgate_ai.harness.httpx.post", fake_post)
    sandbox = LocalSandbox(tmp_path)
    try:
        from skillgate_ai.errors import HarnessError

        with pytest.raises(HarnessError) as caught:
            LLMHarness(_cfg()).run(sandbox, "hello", [], timeout_sec=5)
    finally:
        sandbox.close()
    assert caught.value.message == OFFLINE_MESSAGE
    assert "Errno" not in caught.value.message
    assert "BYO" not in caught.value.message
