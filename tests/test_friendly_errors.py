from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from skillgate_ai.case_pack import CasePack
from skillgate_ai.config import LLMConfig
from skillgate_ai.errors import friendly_validation_error


def _cfg(**overrides: object) -> LLMConfig:
    fields: dict[str, object] = {
        "cursor_api_key": None,
        "gateway_api_key": None,
        "gateway_base_url": "https://api.openai.com/v1",
        "gateway_model": "openai/gpt-4o-mini",
        "anthropic_api_key": None,
        "anthropic_model": "claude-sonnet-4-20250514",
        "cursor_agent_bin": "agent",
        "claude_bin": "claude",
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
