from __future__ import annotations

from dataclasses import replace

import pytest

from skillgate_ai.config import LLMConfig
from skillgate_ai.eval_config import (
    EvalConfigError,
    EvalRunConfig,
    apply_eval_config,
    config_fingerprint,
    config_label,
    diff_eval_config,
    parse_temperature,
    parse_timeout_sec,
    resolve_eval_config,
    stamp_resolved,
    with_timeout_effective,
)


def _llm_config(**overrides: object) -> LLMConfig:
    fields: dict[str, object] = {
        "cursor_api_key": None,
        "gateway_api_key": None,
        "gateway_base_url": "https://ai-gateway.vercel.sh/v1",
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
    }
    fields.update(overrides)
    return LLMConfig(**fields)  # type: ignore[arg-type]


def test_fingerprint_ignores_harness_pref() -> None:
    cfg = _llm_config()
    auto = stamp_resolved(
        resolve_eval_config(harness_pref="auto", incoming={}, cfg=cfg, source="cli"),
        "cursor-agent",
        cfg,
    )
    explicit = stamp_resolved(
        resolve_eval_config(harness_pref="cursor-agent", incoming={}, cfg=cfg, source="cli"),
        "cursor-agent",
        cfg,
    )
    assert config_fingerprint(auto) == config_fingerprint(explicit)
    assert auto.harness_pref == "auto"
    assert explicit.harness_pref == "cursor-agent"


def test_fingerprint_changes_on_knobs() -> None:
    base = EvalRunConfig(harness="codex", model=None, timeout_effective=300, temperature=0.0, reasoning_effort="medium")
    fp = config_fingerprint(base)
    assert config_fingerprint(replace(base, harness="cursor-agent")) != fp
    assert config_fingerprint(replace(base, model="faster")) != fp
    assert config_fingerprint(replace(base, timeout_effective=90)) != fp
    assert config_fingerprint(replace(base, temperature=0.2)) != fp
    assert config_fingerprint(replace(base, reasoning_effort="low")) != fp


def test_fingerprint_ignores_effort_on_non_codex() -> None:
    cursor = EvalRunConfig(harness="cursor-agent", reasoning_effort="ultra", timeout_effective=300)
    cursor_none = EvalRunConfig(harness="cursor-agent", reasoning_effort=None, timeout_effective=300)
    assert config_fingerprint(cursor) == config_fingerprint(cursor_none)


def test_codex_none_effort_fingerprints_as_medium() -> None:
    none = EvalRunConfig(harness="codex", reasoning_effort=None, timeout_effective=300)
    medium = EvalRunConfig(harness="codex", reasoning_effort="medium", timeout_effective=300)
    assert config_fingerprint(none) == config_fingerprint(medium)


def test_blank_timeout_yaml_equals_typed_effective() -> None:
    blank = with_timeout_effective(EvalRunConfig(harness="demo", timeout_sec=None), 300)
    typed = with_timeout_effective(EvalRunConfig(harness="demo", timeout_sec=300), 300)
    assert config_fingerprint(blank) == config_fingerprint(typed)


def test_diff_lists_only_changed_fields() -> None:
    previous = EvalRunConfig(
        harness="cursor-agent",
        model=None,
        timeout_effective=300,
        temperature=0.0,
    )
    current = EvalRunConfig(
        harness="codex",
        model="gpt-test",
        timeout_effective=300,
        temperature=0.0,
        reasoning_effort="low",
    )
    diff = diff_eval_config(current, previous)
    fields = {item["field"] for item in diff}
    assert fields == {"harness", "model", "reasoning_effort"}
    harness = next(item for item in diff if item["field"] == "harness")
    assert harness["from"] == "cursor-agent"
    assert harness["to"] == "codex"


def test_diff_includes_judge_model() -> None:
    previous = EvalRunConfig(
        harness="llm",
        timeout_effective=300,
        judge={"backend": "decisions", "model": "gpt-6-luna"},
    )
    current = EvalRunConfig(
        harness="llm",
        timeout_effective=300,
        judge={"backend": "decisions", "model": "other"},
    )
    diff = diff_eval_config(current, previous)
    fields = {item["field"] for item in diff}
    assert fields == {"judge_model"}


def test_diff_legacy_null_is_empty() -> None:
    current = EvalRunConfig(harness="demo", timeout_effective=12)
    assert diff_eval_config(current, None) == []
    assert diff_eval_config(None, current) == []


def test_apply_eval_config_does_not_mutate_original() -> None:
    cfg = _llm_config(codex_model="env-model", gateway_model="openai/gpt-4o-mini", temperature=0.0)
    run = EvalRunConfig(
        harness="codex",
        model="gpt-test",
        temperature=0.4,
        reasoning_effort="high",
    )
    replaced = apply_eval_config(cfg, run)
    assert cfg.codex_model == "env-model"
    assert cfg.gateway_model == "openai/gpt-4o-mini"
    assert cfg.temperature == 0.0
    assert cfg.codex_reasoning_effort == "medium"
    assert replaced is not cfg
    assert replaced.codex_model == "gpt-test"
    assert replaced.gateway_model == "gpt-test"
    assert replaced.anthropic_model == "gpt-test"
    assert replaced.cursor_model == "gpt-test"
    assert replaced.temperature == 0.4
    assert replaced.codex_reasoning_effort == "high"


def test_apply_without_model_keeps_env_codex_model() -> None:
    cfg = _llm_config(codex_model="from-env")
    run = EvalRunConfig(harness="codex", model=None, reasoning_effort="low")
    replaced = apply_eval_config(cfg, run)
    assert replaced.codex_model == "from-env"
    assert replaced.codex_reasoning_effort == "low"


def test_invalid_timeout_and_temperature() -> None:
    with pytest.raises(EvalConfigError, match="1 and 3600"):
        parse_timeout_sec(0)
    with pytest.raises(EvalConfigError, match="whole number"):
        parse_timeout_sec("nope")
    with pytest.raises(EvalConfigError, match="between 0 and 2"):
        parse_temperature(2.5)


def test_ui_and_cli_reject_invalid_effort() -> None:
    cfg = _llm_config()
    for source in ("ui", "cli"):
        with pytest.raises(EvalConfigError, match="low, medium, high, or ultra"):
            resolve_eval_config(
                harness_pref="codex",
                incoming={"reasoning_effort": "insane"},
                cfg=cfg,
                source=source,
            )


def test_cursor_applies_requested_model() -> None:
    cfg = _llm_config()
    run = resolve_eval_config(
        harness_pref="cursor-agent",
        incoming={"model": "composer-2.5"},
        cfg=cfg,
        source="ui",
        resolved_harness="cursor-agent",
    )
    assert run.model == "composer-2.5"
    assert run.applied["model"] is True
    assert run.applied["temperature"] is False
    replaced = apply_eval_config(cfg, run)
    assert replaced.cursor_model == "composer-2.5"


def test_claude_applies_requested_model() -> None:
    cfg = _llm_config()
    run = resolve_eval_config(
        harness_pref="claude",
        incoming={"model": "claude-sonnet-4-20250514"},
        cfg=cfg,
        source="ui",
        resolved_harness="claude",
    )
    assert run.applied["model"] is True
    assert run.applied["temperature"] is False
    replaced = apply_eval_config(cfg, run)
    assert replaced.anthropic_model == "claude-sonnet-4-20250514"


def test_roundtrip_dict() -> None:
    original = EvalRunConfig(
        harness="codex",
        harness_pref="auto",
        model="gpt-test",
        timeout_sec=90,
        timeout_effective=90,
        temperature=0.2,
        reasoning_effort="low",
        source="ui",
        applied={"harness": True, "model": True, "timeout": True, "temperature": False, "reasoning": True},
    )
    restored = EvalRunConfig.from_dict(original.to_dict())
    assert restored is not None
    assert config_fingerprint(restored) == config_fingerprint(original)
    assert restored.model == "gpt-test"
    assert restored.reasoning_effort == "low"


def test_config_label_includes_harness_and_timeout() -> None:
    run = EvalRunConfig(harness="codex", model="gpt-test", timeout_effective=300, reasoning_effort="medium")
    label = config_label(run)
    assert "Codex" in label
    assert "gpt-test" in label
    assert "300s" in label
    assert "medium" in label


def test_config_label_does_not_say_demo() -> None:
    label = config_label(EvalRunConfig(harness="llm", timeout_effective=12))
    assert "LLM" in label
    assert "demo" not in label.lower()
    assert "Built-in checker" not in label


def test_fingerprint_changes_on_judge_backend() -> None:
    base = EvalRunConfig(harness="llm", timeout_effective=300)
    decisions = replace(
        base,
        judge={"provider": "openai", "backend": "decisions", "model": "gpt-6-luna"},
    )
    responses = replace(
        base,
        judge={"provider": "openai", "backend": "responses", "model": "gpt-6-luna"},
    )
    assert config_fingerprint(base) != config_fingerprint(decisions)
    assert config_fingerprint(decisions) != config_fingerprint(responses)


def test_config_label_names_openai_scorer_not_model_id() -> None:
    run = EvalRunConfig(
        harness="llm",
        timeout_effective=300,
        judge={
            "provider": "openai",
            "backend": "decisions",
            "display_name": "OpenAI (your key)",
            "model": "gpt-6-luna",
        },
    )
    label = config_label(run)
    assert "OpenAI (your key)" in label
    assert "gpt-6-luna" not in label


def test_from_dict_drops_judge_api_key() -> None:
    restored = EvalRunConfig.from_dict(
        {
            "harness": "llm",
            "judge": {
                "provider": "openai",
                "backend": "decisions",
                "api_key": "sk-leak",
            },
        }
    )
    assert restored is not None
    assert restored.judge is not None
    assert "api_key" not in restored.judge
    assert "sk-leak" not in str(restored.to_dict())
