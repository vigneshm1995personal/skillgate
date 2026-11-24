"""Reconcile blocking extra predicates with passing deterministic tool checks."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from skillgate_ai.judge_bank import CHECK_CELL_ORDER
from skillgate_ai.judge_spec import JudgeQuestion
from skillgate_ai.scorers import Score
from skillgate_ai.tool_check_schema import TaskToolChecks, ToolCallRule
from skillgate_ai.tool_checks import TOOL_CHECK_SCORERS

_GENERIC_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "did",
        "does",
        "do",
        "when",
        "asked",
        "agent",
        "skill",
        "gate",
        "was",
        "were",
        "is",
        "has",
        "have",
        "any",
        "use",
        "used",
        "call",
        "called",
        "create",
        "get",
        "list",
        "update",
        "delete",
        "make",
        "tool",
        "stripe",
        "mcp",
    }
)
_NEGATION_TOKENS = frozenset({"not", "never", "twice", "avoid", "without", "skip", "bypass"})
_PROPERTY_TOKENS = frozenset(
    {
        "amount",
        "correct",
        "right",
        "exact",
        "only",
        "twice",
        "once",
        "without",
        "before",
        "after",
        "value",
        "id",
        "number",
        "issued",
        "invoice",
        "fee",
        "total",
        "equal",
        "match",
        "matching",
        "precise",
        "duplicate",
    }
)


def _tokens(text: str) -> set[str]:
    parts = re.split(r"[^a-z0-9]+", text.lower())
    out: set[str] = set()
    for part in parts:
        if len(part) < 3 or part in _GENERIC_WORDS:
            continue
        out.add(part)
        if part.endswith("s") and len(part) > 4:
            out.add(part[:-1])
    return out


def _rule_passed(facts: Mapping[str, Any], tool: str) -> dict[str, Any] | None:
    rules = facts.get("must_call_rules")
    if not isinstance(rules, list):
        return None
    want = tool.strip().lower()
    for row in rules:
        if not isinstance(row, Mapping):
            continue
        if str(row.get("tool") or "").strip().lower() == want and row.get("passed"):
            return dict(row)
    return None


def tool_check_rule_results(scores: Sequence[Score]) -> list[dict[str, Any]]:
    for score in scores:
        if score.scorer != "tool_calls" or not isinstance(score.facts, dict):
            continue
        rules = score.facts.get("must_call_rules")
        if isinstance(rules, list):
            return [dict(item) for item in rules if isinstance(item, Mapping)]
    return []


def _question_segments(qid: str) -> list[str]:
    return [seg for seg in qid.lower().split("_") if seg]


def _asserts_beyond_action_taken(qid: str) -> bool:
    segments = _question_segments(qid)
    return bool(_PROPERTY_TOKENS & set(segments) or _NEGATION_TOKENS & set(segments))


def question_overlaps_rule(
    question: JudgeQuestion,
    rule: ToolCallRule | Mapping[str, Any],
    *,
    rule_row: Mapping[str, Any] | None = None,
) -> bool:
    if question.type != "predicate" or question.on_fail != "block":
        return False
    qid = question.id.lower()
    if any(token in _question_segments(qid) for token in _NEGATION_TOKENS):
        return False
    tool = str(rule.get("tool") if isinstance(rule, Mapping) else rule.tool)
    if any(ch in tool for ch in "*?[]"):
        return False
    explicit = question.covered_by
    if explicit is not None:
        if not explicit:
            return False
        tool_l = tool.lower()
        if not any(pat.strip().lower() == tool_l for pat in explicit):
            return False
        if _asserts_beyond_action_taken(qid):
            pinned = rule_row.get("args_pinned") if isinstance(rule_row, Mapping) else None
            return bool(pinned)
        return True
    if _asserts_beyond_action_taken(qid):
        return False
    q_words = _tokens(question.id)
    t_words = _tokens(tool)
    return bool(q_words & t_words)


def _builtin_cells_pass(judged: Mapping[str, Any]) -> bool:
    cells = judged.get("cells")
    if not isinstance(cells, dict):
        return False
    for key in CHECK_CELL_ORDER:
        cell = cells.get(key)
        if not isinstance(cell, dict):
            return False
        choice = str(cell.get("choice") or "").strip().lower()
        if choice in ("", "incorrect", "wrong", "failed", "no"):
            return False
    return True


def reconcile_tool_covered_extras(
    judged: dict[str, Any] | None,
    scores: Sequence[Score],
    *,
    tool_checks: TaskToolChecks | None,
    extras: Sequence[JudgeQuestion] | None = None,
) -> dict[str, Any] | None:
    """Drop or downgrade extra failures contradicted by passing must_call rules."""
    if not isinstance(judged, dict):
        return judged
    failures = judged.get("extra_failures")
    if not isinstance(failures, list) or not failures:
        return judged
    if any(not s.passed for s in scores if s.scorer in TOOL_CHECK_SCORERS):
        return judged
    if any(s.scorer == "skill_trigger" and not s.passed for s in scores):
        return judged
    rule_rows = tool_check_rule_results(scores)
    if not rule_rows:
        return judged
    checks = tool_checks if tool_checks is not None else TaskToolChecks()
    rules_by_tool = {str(r.tool): r for r in checks.must_call}
    id_map = judged.get("extra_failure_ids")
    if not isinstance(id_map, dict):
        id_map = {}
    extra_by_id = {q.id: q for q in (extras or []) if not q.builtin}
    reconciled_details: list[str] = []
    needs_review = False
    for qid, detail in list(id_map.items()):
        question = extra_by_id.get(str(qid))
        if question is None:
            continue
        matched_rule: dict[str, Any] | None = None
        for row in rule_rows:
            if not row.get("passed"):
                continue
            tool = str(row.get("tool") or "")
            rule: ToolCallRule | Mapping[str, Any] = rules_by_tool.get(tool) or {"tool": tool}
            if question_overlaps_rule(question, rule, rule_row=row):
                matched_rule = row
                break
        if matched_rule is None:
            continue
        text = str(detail or "").strip()
        if text:
            reconciled_details.append(text)
        if matched_rule.get("args_pinned"):
            continue
        needs_review = True
    if not reconciled_details:
        return judged
    out = dict(judged)
    remaining = [item for item in failures if str(item).strip() not in reconciled_details]
    out["extra_failures"] = remaining
    reasons = [str(item) for item in (out.get("reasons") or []) if str(item).strip()]
    out["reasons"] = [item for item in reasons if item not in reconciled_details]
    out["tool_predicate_reconciled"] = reconciled_details
    if needs_review:
        out["review"] = True
    if not remaining and _builtin_cells_pass(out):
        out["passed"] = True
    return out


def format_verified_tool_checks(scores: Sequence[Score]) -> str:
    lines: list[str] = []
    for score in scores:
        if score.scorer not in TOOL_CHECK_SCORERS:
            continue
        mark = "passed" if score.passed else "failed"
        headline = (score.headline or score.detail or "").strip()
        lines.append(f"- {score.scorer}: {mark}" + (f" ({headline})" if headline else ""))
        for row in tool_check_rule_results(scores):
            tool = str(row.get("tool") or "")
            if not tool:
                continue
            detail = "passed" if row.get("passed") else "failed"
            args = row.get("args_match")
            if args:
                detail += f" with args {args}"
            lines.append(f"  - must_call {tool}: {detail}")
    if not lines:
        return ""
    return "Verified tool checks (deterministic, from the run log):\n" + "\n".join(lines)
