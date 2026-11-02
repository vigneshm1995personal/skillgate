from __future__ import annotations

import pytest

from skillgate_ai.config import (
    DEFAULT_GATEWAY_MODEL,
    DEFAULT_JUDGE_BACKEND,
    DEFAULT_JUDGE_MODEL,
    LLMConfig,
)
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.engine import _live_verdict, _maybe_explain_fail
from skillgate_ai.output_match import REASON_MISSING_OUTPUT
from skillgate_ai.judge import SkipJudge, judge_stamp, resolve_judge
from skillgate_ai.judge_bank import LOW_CONFIDENCE_WARNING
from skillgate_ai.judge_openai import OutcomeJudge, make_openai_judge


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
        "harness_pref": "auto",
        "sandbox_pref": "local",
        "docker_image": "skillgate-sandbox:v0",
        "openai_api_key": None,
    }
    fields.update(overrides)
    return LLMConfig(**fields)  # type: ignore[arg-type]


def test_skip_judge_does_not_pass_or_fail() -> None:
    judged = SkipJudge().judge(
        "extract hello.pdf", [{"path": "out.txt", "present": True}], "selected: pdf"
    )
    assert judged["status"] == "skip"
    assert judged["passed"] is None
    assert judged["cells"] == []
    assert judged["display_name"] == "Checks"


def test_resolve_judge_auto_asks_for_a_decision_model() -> None:
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(_cfg(), harness_name="cursor-agent")
    assert "Pick a decision model" in caught.value.message
    assert caught.value.exit_code == 2


def test_resolve_judge_auto_does_not_use_a_saved_key() -> None:
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(_cfg(openai_api_key="sk-test"), harness_name="cursor-agent")
    assert "Pick a decision model" in caught.value.message


def test_resolve_judge_skip_is_not_a_live_judge() -> None:
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(
            _cfg(openai_api_key="sk-test", judge_pref="skip"),
            harness_name="cursor-agent",
        )
    assert "Pick a decision model" in caught.value.message


def test_resolve_judge_demo_always_skips() -> None:
    judge = resolve_judge(_cfg(openai_api_key="sk-test"), harness_name="demo")
    assert isinstance(judge, SkipJudge)


def test_resolve_judge_openai_without_key() -> None:
    with pytest.raises(MissingLLMKeyError) as caught:
        resolve_judge(_cfg(judge_pref="openai"), harness_name="cursor-agent")
    assert caught.value.exit_code == 2
    assert "API key" in caught.value.message
    assert "OpenAI" not in caught.value.message


def test_missing_provider_key_uses_add_your() -> None:
    from skillgate_ai.judge import missing_provider_key

    aws = missing_provider_key("aws")
    assert "API key" in aws.message
    assert "AWS" not in aws.message
    other = missing_provider_key("compatible")
    assert "API key" in other.message
    assert "Other" not in other.message
    assert "AI_GATEWAY_API_KEY" not in other.message
    assert "gateway" not in other.message.lower()


def test_resolve_judge_openai_pref_ignores_gateway_key() -> None:
    with pytest.raises(MissingLLMKeyError) as caught:
        resolve_judge(
            _cfg(
                gateway_api_key="gw-test",
                judge_pref="openai",
                gateway_base_url="https://ai-gateway.vercel.sh/v1",
            ),
            harness_name="cursor-agent",
        )
    assert "API key" in caught.value.message
    assert "OpenAI" not in caught.value.message
    assert "gateway" not in caught.value.message.lower()


def test_gateway_key_does_not_select_a_judge() -> None:
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(
            _cfg(
                gateway_api_key="gw-test",
                gateway_base_url="https://ai-gateway.vercel.sh/v1",
            ),
            harness_name="cursor-agent",
        )
    assert "Pick a decision model" in caught.value.message


def test_openai_key_keeps_judge_on_openai_decisions() -> None:
    judge = resolve_judge(
        _cfg(
            openai_api_key="sk-test",
            gateway_api_key="gw-test",
            gateway_base_url="https://ai-gateway.vercel.sh/v1",
            judge_pref="openai",
            judge_provider="openai",
            judge_chosen=True,
        ),
        harness_name="cursor-agent",
    )
    assert isinstance(judge, OutcomeJudge)
    assert judge.backend.name == "decisions"
    assert judge.backend.api_key == "sk-test"
    assert judge.backend.base_url.endswith("api.openai.com/v1")
    assert judge.backend.model == "gpt-6-luna"


def test_default_scoring_uses_decisions_not_the_task_model() -> None:
    assert DEFAULT_JUDGE_BACKEND == "decisions"
    assert DEFAULT_JUDGE_MODEL == "gpt-6-luna"
    assert DEFAULT_GATEWAY_MODEL == "openai/gpt-4o-mini"

    direct = resolve_judge(
        _cfg(
            openai_api_key="sk-test",
            gateway_model=DEFAULT_GATEWAY_MODEL,
            judge_pref="openai",
        ),
        harness_name="cursor-agent",
    )
    assert isinstance(direct, OutcomeJudge)
    assert direct.backend.name == "decisions"
    assert direct.backend.model == DEFAULT_JUDGE_MODEL
    assert direct.backend.model != DEFAULT_GATEWAY_MODEL

    with pytest.raises(SkillGateError) as caught:
        resolve_judge(
            _cfg(
                gateway_api_key="gw-test",
                gateway_base_url="https://ai-gateway.vercel.sh/v1",
                gateway_model=DEFAULT_GATEWAY_MODEL,
            ),
            harness_name="cursor-agent",
        )
    assert "Pick a decision model" in caught.value.message


def test_judge_stamp_has_no_secret() -> None:
    stamp = judge_stamp(
        resolve_judge(
            _cfg(openai_api_key="sk-secret", judge_pref="openai"),
            harness_name="cursor-agent",
        )
    )
    blob = str(stamp)
    assert "sk-secret" not in blob
    assert stamp["provider"] == "openai"
    assert stamp["backend"] == "decisions"
    assert stamp["display_name"] == "the judge"
    assert stamp["model"] == "gpt-6-luna"


def test_gateway_key_does_not_stamp_a_judge() -> None:
    with pytest.raises(SkillGateError) as caught:
        resolve_judge(
            _cfg(
                gateway_api_key="gw-test",
                gateway_base_url="https://ai-gateway.vercel.sh/v1",
            ),
            harness_name="cursor-agent",
        )
    assert "Pick a decision model" in caught.value.message
    assert "gw-test" not in caught.value.message
    assert "fallback" not in caught.value.message.lower()


def test_judge_stamp_uses_decisions_backend_model() -> None:
    judge = make_openai_judge(api_key="sk-test", model="not-the-decisions-model")
    stamp = judge_stamp(judge)
    assert stamp["model"] == "gpt-6-luna"
    assert "not-the-decisions-model" not in str(stamp)


def test_live_verdict_skip_keeps_det() -> None:
    passed, failures, _ = _live_verdict(
        {"status": "skip", "passed": None},
        "pdf",
        det_passed=True,
        det_failures=[],
    )
    assert passed is True
    assert failures == []


def test_live_verdict_error_is_not_passed_when_det_green() -> None:
    passed, failures, stamped = _live_verdict(
        {"status": "error", "passed": False, "reasons": ["The judge couldn't score this check (HTTP 402)."]},
        "pdf",
        det_passed=True,
        det_failures=[],
    )
    assert passed is None
    assert failures == ["The judge couldn't score this check (HTTP 402)."]
    assert stamped is not None
    assert stamped.get("quality_unscored") is True
    assert stamped.get("passed") is None


def test_live_verdict_error_still_fails_when_det_fails() -> None:
    passed, failures, stamped = _live_verdict(
        {"status": "error", "reasons": ["The judge scoring timed out."]},
        "pdf",
        det_passed=False,
        det_failures=["Skill didn't trigger"],
    )
    assert passed is False
    assert failures == ["Skill didn't trigger"]
    assert stamped is not None
    assert stamped.get("quality_unscored") is True


def test_live_verdict_score_no_trigger_extras_can_fail() -> None:
    judge = {
        "status": "completed",
        "passed": False,
        "reasons": ["Do the totals match? No"],
        "extra_failures": ["Do the totals match? No"],
        "score_no_trigger": True,
        "warnings": [],
    }
    passed, failures, _ = _live_verdict(
        judge,
        None,
        det_passed=True,
        det_failures=[],
    )
    assert passed is False
    assert failures == ["Do the totals match? No"]


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


def test_live_verdict_no_trigger_ignores_judge_error_and_missing_output() -> None:
    judge = {
        "status": "error",
        "passed": False,
        "reasons": ["OpenAI scoring returned an unusable answer."],
        "warnings": [],
    }
    passed, failures, stamped = _live_verdict(
        judge,
        None,
        det_passed=True,
        det_failures=[],
        mismatch=REASON_MISSING_OUTPUT,
    )
    assert passed is True
    assert failures == []
    assert stamped is not None


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
    }
    passed, failures, stamped = _live_verdict(
        judge,
        "pdf",
        det_passed=True,
        det_failures=[],
        mismatch=REASON_MISSING_OUTPUT,
    )
    assert passed is False
    assert REASON_MISSING_OUTPUT in failures
    assert stamped is not None
    assert stamped["passed"] is True


def test_live_verdict_mismatch_ignores_judge_blob() -> None:
    judge = {
        "status": "completed",
        "passed": True,
        "reasons": [],
        "warnings": [],
        "golden": {"path": "out.json", "kind": "json"},
        "actual_output": {"path": "out.json", "present": False},
    }
    passed, failures, stamped = _live_verdict(
        judge,
        "pdf",
        det_passed=True,
        det_failures=[],
        mismatch=None,
    )
    assert passed is True
    assert failures == []
    assert stamped is not None
    assert stamped["passed"] is True


def test_explain_fail_runs_only_after_gate_fail() -> None:
    class Explainer:
        def explain_fail(
            self,
            reasons: list[str],
            *,
            judged=None,
            check="",
            transcript_tail="",
            expected_output=None,
            actual_output=None,
        ) -> str:
            assert reasons == ["missing"]
            assert check == "extract"
            return "The expected file was missing."

    judged = {"status": "completed", "passed": True, "reasons": []}
    assert (
        _maybe_explain_fail(
            Explainer(),
            True,
            ["missing"],
            judged,
            check="extract",
            transcript_tail="",
        )
        == judged
    )
    failed = _maybe_explain_fail(
        Explainer(),
        False,
        ["missing"],
        judged,
        check="extract",
        transcript_tail="",
    )
    assert failed is not None
    assert failed["why"] == "The expected file was missing."
