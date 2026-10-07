from __future__ import annotations

import pytest

from skillgate_ai.config import LLMConfig
from skillgate_ai.errors import MissingLLMKeyError
from skillgate_ai.engine import REASON_MISSING_OUTPUT, _live_verdict
from skillgate_ai.judge import SkipJudge, judge_stamp, resolve_judge
from skillgate_ai.judge_bank import LOW_CONFIDENCE_WARNING
from skillgate_ai.judge_openai import OutcomeJudge


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
        "harness_pref": "auto",
        "sandbox_pref": "local",
        "docker_image": "skillgate-sandbox:v0",
        "openai_api_key": None,
    }
    fields.update(overrides)
    return LLMConfig(**fields)  # type: ignore[arg-type]


def test_skip_judge_does_not_pass_or_fail() -> None:
    judged = SkipJudge().judge("extract hello.pdf", [{"path": "out.txt", "present": True}], "selected: pdf")
    assert judged["status"] == "skip"
    assert judged["passed"] is None
    assert judged["cells"] == []
    assert judged["display_name"] == "Built-in checker"


def test_resolve_judge_auto_skips_without_key() -> None:
    judge = resolve_judge(_cfg(), harness_name="llm")
    assert isinstance(judge, SkipJudge)


def test_resolve_judge_auto_openai_on_live() -> None:
    judge = resolve_judge(_cfg(openai_api_key="sk-test"), harness_name="llm")
    assert isinstance(judge, OutcomeJudge)
    assert judge.backend.name == "decisions"


def test_resolve_judge_skip_override() -> None:
    judge = resolve_judge(
        _cfg(openai_api_key="sk-test", judge_pref="skip"),
        harness_name="llm",
    )
    assert isinstance(judge, SkipJudge)


def test_resolve_judge_demo_always_skips() -> None:
    judge = resolve_judge(_cfg(openai_api_key="sk-test"), harness_name="demo")
    assert isinstance(judge, SkipJudge)


def test_resolve_judge_openai_without_key() -> None:
    with pytest.raises(MissingLLMKeyError) as caught:
        resolve_judge(_cfg(judge_pref="openai"), harness_name="llm")
    assert caught.value.exit_code == 2
    assert "OpenAI API key" in caught.value.message


def test_gateway_key_is_not_an_openai_judge_key() -> None:
    judge = resolve_judge(_cfg(gateway_api_key="gw-test"), harness_name="llm")
    assert isinstance(judge, SkipJudge)


def test_judge_stamp_has_no_secret() -> None:
    stamp = judge_stamp(resolve_judge(_cfg(openai_api_key="sk-secret"), harness_name="llm"))
    blob = str(stamp)
    assert "sk-secret" not in blob
    assert stamp["provider"] == "openai"
    assert stamp["backend"] == "decisions"
    assert stamp["display_name"] == "OpenAI (your key)"


def test_live_verdict_skip_keeps_det() -> None:
    passed, failures, _ = _live_verdict(
        {"status": "skip", "passed": None},
        "pdf",
        det_passed=True,
        det_failures=[],
    )
    assert passed is True
    assert failures == []


def test_live_verdict_error_fails_closed() -> None:
    passed, failures, stamped = _live_verdict(
        {"status": "error", "passed": False, "reasons": ["OpenAI did not accept this API key. Check OPENAI_API_KEY."]},
        "pdf",
        det_passed=True,
        det_failures=[],
    )
    assert passed is False
    assert "OpenAI did not accept this API key" in failures[0]
    assert stamped is not None and stamped["passed"] is False


def test_live_verdict_no_trigger_det_owns() -> None:
    judge = {
        "status": "completed",
        "passed": False,
        "reasons": ["Got the job done? Not completed (need Fully completed)"],
        "warnings": [],
    }
    passed, failures, stamped = _live_verdict(
        judge,
        None,
        det_passed=True,
        det_failures=[],
    )
    assert passed is True
    assert failures == []
    assert stamped is not None
    assert stamped["passed"] is False


def test_live_verdict_low_confidence_keeps_pass() -> None:
    judge = {
        "status": "completed",
        "passed": True,
        "reasons": [],
        "warnings": [LOW_CONFIDENCE_WARNING],
    }
    passed, failures, stamped = _live_verdict(
        judge,
        "pdf",
        det_passed=True,
        det_failures=[],
    )
    assert passed is True
    assert failures == []
    assert stamped is not None
    assert stamped["warnings"] == [LOW_CONFIDENCE_WARNING]


def test_live_verdict_mismatch_still_fails() -> None:
    judge = {
        "status": "completed",
        "passed": True,
        "reasons": [],
        "warnings": [],
        "golden": {"path": "out.json", "kind": "json"},
        "actual_output": {"path": "out.json", "present": False},
    }
    passed, failures, _ = _live_verdict(
        judge,
        "pdf",
        det_passed=True,
        det_failures=[],
    )
    assert passed is False
    assert REASON_MISSING_OUTPUT in failures
