"""Deterministic tool-call checks (unit)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from skillgate_ai.suite import TaskSpec
from skillgate_ai.tool_check_schema import TaskToolChecks, ToolCallRule
from skillgate_ai.tool_checks import (
    ToolCall,
    collect_tool_calls,
    is_consequential,
    matches_pattern,
    normalize_tool_name,
    score_tool_checks,
    tool_aliases,
    tool_check_failures,
)


def _write_calls_log(ws: Path, rows: list[dict]) -> None:
    dest = ws / "output"
    dest.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(row, ensure_ascii=True) for row in rows]
    (dest / "calls.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _span(tool: str, args: str | dict) -> dict:
    args_text = json.dumps(args) if isinstance(args, dict) else args
    return {
        "name": f"tool.{tool}",
        "attributes": [
            {"key": "gen_ai.tool.name", "value": {"stringValue": tool}},
            {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": args_text}},
        ],
    }


def _task(**tool_checks: object) -> TaskSpec:
    checks = TaskToolChecks(**tool_checks) if tool_checks else None
    return TaskSpec(id="c", prompt="p", expect_skill="demo", scorers=[], tool_checks=checks)


def test_normalize_tool_name_camel_and_separators() -> None:
    assert normalize_tool_name("chat.postMessage") == "chat_post_message"
    assert normalize_tool_name("Stripe-Refunds Create") == "stripe_refunds_create"


def test_mcp_aliases() -> None:
    aliases = tool_aliases("mcp__stripe__refunds_create")
    assert "mcp__stripe__refunds_create" in aliases
    assert "stripe_refunds_create" in aliases
    assert "refunds_create" in aliases


def test_glob_pattern_matches_any_alias() -> None:
    call = ToolCall(
        name="mcp__gmail__send_message",
        aliases=tool_aliases("mcp__gmail__send_message"),
        args={},
        source="span",
        label="tool span",
    )
    assert matches_pattern(call, "gmail_*")
    assert matches_pattern(call, "send_*")
    assert not matches_pattern(call, "slack_*")


def test_collect_from_calls_log_tool_field(tmp_path: Path) -> None:
    _write_calls_log(tmp_path, [{"tool": "stripe_refunds_create", "args": {"amount": 4900}}])
    calls = collect_tool_calls(tmp_path, None, "")
    assert len(calls) == 1
    assert calls[0].source == "calls_log"
    assert calls[0].args == {"amount": 4900}


def test_collect_from_calls_log_argv(tmp_path: Path) -> None:
    _write_calls_log(
        tmp_path,
        [{"argv": ["python", "tools.py", "issue_refund", "--amount", "49.00"]}],
    )
    calls = collect_tool_calls(tmp_path, None, "")
    assert any("issue_refund" in alias for call in calls for alias in call.aliases)


def test_collect_skips_bad_lines(tmp_path: Path) -> None:
    dest = tmp_path / "output"
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "calls.log").write_text("not json\n[]\n", encoding="utf-8")
    assert collect_tool_calls(tmp_path, None, "") == []


def test_must_call_not_called(tmp_path: Path) -> None:
    task = _task(must_call=[{"tool": "stripe_charges_list"}])
    scores = score_tool_checks(task, tmp_path, spans=None, transcript="")
    tool_scores = [s for s in scores if s.scorer == "tool_calls"]
    assert len(tool_scores) == 1
    assert tool_scores[0].passed is False
    assert tool_scores[0].headline.startswith("Must call stripe_charges_list: not called")


def test_must_not_call_hits(tmp_path: Path) -> None:
    _write_calls_log(tmp_path, [{"tool": "stripe_refunds_create", "args": {}}])
    task = _task(must_not_call=["stripe_refunds_create"])
    scores = score_tool_checks(task, tmp_path, spans=None, transcript="")
    tool_scores = [s for s in scores if s.scorer == "tool_calls"]
    assert tool_scores[0].passed is False
    assert "Must not call stripe_refunds_create" in tool_scores[0].headline


def test_args_match_scalar_numeric_coercion(tmp_path: Path) -> None:
    _write_calls_log(tmp_path, [{"tool": "stripe_refunds_create", "args": {"amount": "4900"}}])
    task = _task(must_call=[{"tool": "stripe_refunds_create", "args_match": {"amount": 4900}}])
    scores = score_tool_checks(task, tmp_path, spans=None, transcript="")
    assert scores[0].passed is True


def test_args_match_missing_key_fails(tmp_path: Path) -> None:
    _write_calls_log(tmp_path, [{"tool": "stripe_refunds_create", "args": {"amount": 4900}}])
    task = _task(must_call=[{"tool": "stripe_refunds_create", "args_match": {"amount": 100}}])
    scores = score_tool_checks(task, tmp_path, spans=None, transcript="")
    assert scores[0].passed is False
    assert "no call matched" in scores[0].detail


def test_invalid_regex_is_load_error() -> None:
    with pytest.raises(ValidationError):
        ToolCallRule.model_validate(
            {"tool": "x", "args_match": {"a": {"regex": "("}}},
        )


def test_calls_log_path_escape_rejected() -> None:
    with pytest.raises(ValidationError):
        TaskToolChecks(calls_log="../x.log")


@pytest.mark.parametrize(
    "name,expected",
    [
        ("gmail_send_message", True),
        ("stripe_refunds_create", True),
        ("issue_refund", True),
        ("gmail_create_draft", False),
        ("stripe_refunds_list", False),
        ("delete_file", False),
        ("read_file", False),
    ],
)
def test_builtin_consequential_names(name: str, expected: bool) -> None:
    call = ToolCall(
        name=name,
        aliases=tool_aliases(name),
        args={},
        source="span",
        label="tool span",
    )
    assert is_consequential(call, pack_patterns=(), builtin=True) is expected


def test_allow_consequential_allows(tmp_path: Path) -> None:
    _write_calls_log(tmp_path, [{"tool": "gmail_send_message", "args": {}}])
    task = _task(allow_consequential=["gmail_send_message"])
    scores = score_tool_checks(task, tmp_path, spans=None, transcript="")
    cons = [s for s in scores if s.scorer == "consequential_calls"]
    assert cons[0].passed is True


def test_default_task_runs_consequential(tmp_path: Path) -> None:
    _write_calls_log(tmp_path, [{"tool": "gmail_send_message", "args": {}}])
    task = TaskSpec(id="c", prompt="p", expect_skill="demo", scorers=[], tool_checks=None)
    scores = score_tool_checks(task, tmp_path, spans=None, transcript="")
    cons = [s for s in scores if s.scorer == "consequential_calls"]
    assert cons[0].passed is False


def test_skip_consequential_check_omits_score(tmp_path: Path) -> None:
    _write_calls_log(tmp_path, [{"tool": "gmail_send_message", "args": {}}])
    task = _task(skip_consequential_check=True)
    scores = score_tool_checks(task, tmp_path, spans=None, transcript="")
    assert not [s for s in scores if s.scorer == "consequential_calls"]


def test_shell_rule_azd_up() -> None:
    spans = [_span("shell", "cd app && azd up")]
    calls = collect_tool_calls(Path("/tmp"), spans, "")
    assert any(call.name == "shell:azd_up" for call in calls)


def test_shell_echo_azd_up_is_not_a_call() -> None:
    spans = [_span("shell", 'echo "azd up"')]
    calls = collect_tool_calls(Path("/tmp"), spans, "")
    assert not any(call.name == "shell:azd_up" for call in calls)


def test_shell_echo_git_push_is_not_a_call() -> None:
    spans = [_span("shell", "echo git push origin main")]
    calls = collect_tool_calls(Path("/tmp"), spans, "")
    assert not any(call.name == "shell:git_push" for call in calls)


def test_allow_consequential_azd_up_waives_shell_rule(tmp_path: Path) -> None:
    spans = [_span("shell", "azd up")]
    task = _task(allow_consequential=["azd up"])
    scores = score_tool_checks(task, tmp_path, spans=spans, transcript="")
    cons = [s for s in scores if s.scorer == "consequential_calls"]
    assert cons[0].passed is True


def test_must_call_allows_consequential_without_allow_list(tmp_path: Path) -> None:
    _write_calls_log(tmp_path, [{"tool": "stripe_refunds_create", "args": {}}])
    task = _task(must_call=["stripe_refunds_create"])
    scores = score_tool_checks(task, tmp_path, spans=None, transcript="")
    cons = [s for s in scores if s.scorer == "consequential_calls"]
    assert cons[0].passed is True


def test_tool_check_failures_uses_scorer_headlines(tmp_path: Path) -> None:
    _write_calls_log(tmp_path, [{"tool": "stripe_refunds_create", "args": {}}])
    scores = score_tool_checks(_task(), tmp_path, spans=None, transcript="")
    failures = tool_check_failures(scores)
    assert failures
    assert failures[0].startswith("Unrequested consequential call: stripe_refunds_create")
    assert "allow_consequential" in failures[0]
