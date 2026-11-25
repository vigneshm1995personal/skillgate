from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.config import get_llm_config, normalize_codex_reasoning_effort
from skillgate_ai.keys import set_vault_key


def test_gateway_base_url_when_gateway_key_set(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    set_vault_key(tmp_path, "AI_GATEWAY_API_KEY", "gw-secret")
    bind = __import__("skillgate_ai.keys", fromlist=["bind_key_env"]).bind_key_env
    bind(["AI_GATEWAY_API_KEY"])
    cfg = get_llm_config(tmp_path)
    assert cfg.gateway_api_key == "gw-secret"
    assert "vercel" in cfg.gateway_base_url or "gateway" in cfg.gateway_base_url


def test_explicit_gateway_base_url_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SKILLGATE_ROOT", str(tmp_path))
    monkeypatch.setenv("AI_GATEWAY_BASE_URL", "https://gw.example/v1/")
    cfg = get_llm_config(tmp_path)
    assert cfg.gateway_base_url == "https://gw.example/v1"


@pytest.mark.parametrize("value", ["low", "medium", "high", "ultra", ""])
def test_normalize_codex_reasoning_effort_accepts_set(value: str) -> None:
    got = normalize_codex_reasoning_effort(value)
    assert got in {"low", "medium", "high", "ultra"}
