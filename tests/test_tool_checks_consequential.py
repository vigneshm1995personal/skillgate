from __future__ import annotations

from skillgate_ai.tool_check_schema import TaskToolChecks, ToolCallRule
from skillgate_ai.tool_checks.aliases import ToolCall
from skillgate_ai.tool_checks.consequential import (
    _allow_consequential_hint,
    _allowed_consequential,
    _consequential_display_name,
    _score_consequential,
    is_consequential,
)


def _call(name: str, *, source: str = "span") -> ToolCall:
    return ToolCall(
        name=name,
        aliases=frozenset({name}),
        args={},
        source=source,
        label="tool",
    )


def test_is_consequential_matches_pack_pattern() -> None:
    call = _call("stripe_refunds_create")
    assert is_consequential(call, pack_patterns=["stripe_refunds_create"], builtin=False) is True


def test_is_consequential_detects_shell_builtin() -> None:
    call = _call("shell:rm")
    assert is_consequential(call, pack_patterns=[], builtin=True) is True


def test_is_consequential_ignores_safe_tools() -> None:
    call = _call("read")
    assert is_consequential(call, pack_patterns=[], builtin=True) is False


def test_allowed_consequential_respects_must_call() -> None:
    call = _call("stripe_refunds_create")
    checks = TaskToolChecks(must_call=[ToolCallRule(tool="stripe_refunds_create", min=1)])
    assert _allowed_consequential(call, checks) is True


def test_score_consequential_reports_unrequested_call() -> None:
    call = _call("stripe_charges_create")
    checks = TaskToolChecks(builtin_consequential=True)
    score = _score_consequential(checks, [call])
    assert score.passed is False
    assert "consequential" in (score.detail or "").lower()


def test_allow_consequential_hint_and_display_name() -> None:
    call = _call("shell:deploy_release")
    assert _consequential_display_name(call)
    assert "deploy" in _allow_consequential_hint(call)
