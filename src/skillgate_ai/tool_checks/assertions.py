from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from skillgate_ai.scorers import Score
from skillgate_ai.tool_check_schema import TaskToolChecks, ToolCallRule
from skillgate_ai.tool_checks.aliases import ToolCall, matches_pattern


def _get_path(data: Mapping[str, Any] | str, path: str) -> Any:
    if not isinstance(data, dict):
        return None
    cur: Any = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _match_expected(actual: Any, expected: Any, *, string_mode: bool) -> bool:
    if isinstance(expected, dict):
        if "equals" in expected:
            return _match_expected(actual, expected["equals"], string_mode=string_mode)
        if "contains" in expected:
            return str(expected["contains"]) in str(actual)
        if "regex" in expected:
            return bool(re.search(str(expected["regex"]), str(actual)))
        return False
    if string_mode:
        return False
    if isinstance(expected, bool):
        return bool(actual) == expected
    if isinstance(expected, (int, float)) and actual is not None:
        try:
            return float(actual) == float(expected)
        except (TypeError, ValueError):
            return False
    return actual == expected


def _args_match(call: ToolCall, spec: dict[str, Any] | None) -> bool:
    if not spec:
        return True
    string_args = not isinstance(call.args, dict)
    for key, expected in spec.items():
        if string_args:
            if not _match_expected(call.args, expected, string_mode=True):
                return False
            continue
        actual = _get_path(call.args, key)
        if not _match_expected(actual, expected, string_mode=False):
            return False
    return True


def _matching_calls(calls: Sequence[ToolCall], rule: ToolCallRule) -> list[ToolCall]:
    return [
        call
        for call in calls
        if matches_pattern(call, rule.tool) and _args_match(call, rule.args_match)
    ]


def _count_matching(calls: Sequence[ToolCall], rule: ToolCallRule) -> int:
    matching = _matching_calls(calls, rule)
    by_source: dict[str, int] = {"calls_log": 0, "span": 0, "shell": 0}
    for call in matching:
        by_source[call.source] = by_source.get(call.source, 0) + 1
    return max(by_source.values()) if matching else 0


def _fmt_args(spec: dict[str, Any] | None) -> str:
    if not spec:
        return ""
    parts = []
    for key, val in spec.items():
        parts.append(f"{key}={val!r}")
    return "{" + ", ".join(parts) + "}"


def _score_assertions(checks: TaskToolChecks, calls: Sequence[ToolCall]) -> Score:
    failures: list[str] = []
    rule_rows: list[dict[str, Any]] = []
    for rule in checks.must_call:
        matching = _matching_calls(calls, rule)
        pattern_hits = [call for call in calls if matches_pattern(call, rule.tool)]
        count = _count_matching(calls, rule)
        rule_failed = False
        if count < rule.min:
            rule_failed = True
            if count == 0:
                if rule.args_match and pattern_hits:
                    failures.append(
                        f"Must call {rule.tool} with {_fmt_args(rule.args_match)}: "
                        f"called {len(pattern_hits)}, no call matched"
                    )
                else:
                    failures.append(f"Must call {rule.tool}: not called")
            else:
                failures.append(
                    f"Must call {rule.tool} at least {rule.min} time(s): called {count}"
                )
        elif rule.max is not None and count > rule.max:
            rule_failed = True
            failures.append(f"Must call {rule.tool} at most {rule.max} time(s): called {count}")
        elif rule.args_match and not matching:
            rule_failed = True
            failures.append(
                f"Must call {rule.tool} with {_fmt_args(rule.args_match)}: "
                f"called {count}, no call matched"
            )
        rule_rows.append(
            {
                "tool": rule.tool,
                "passed": not rule_failed,
                "min": rule.min,
                "count": count,
                "args_match": dict(rule.args_match) if rule.args_match else None,
                "args_pinned": bool(rule.args_match and not rule_failed),
            }
        )
    for rule in checks.must_not_call:
        matches = _matching_calls(calls, rule)
        if matches:
            call = matches[0]
            failures.append(f"Must not call {rule.tool}: called {len(matches)} ({call.label})")
    passed = not failures
    detail = "Tool calls matched" if passed else "; ".join(failures)
    actual_names = sorted({call.name for call in calls})[:20]
    return Score(
        scorer="tool_calls",
        passed=passed,
        detail=detail,
        expected="tool call rules",
        actual=", ".join(actual_names) if actual_names else "none",
        facts={"must_call_rules": rule_rows},
    )
