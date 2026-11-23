from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from skillgate_ai.judge_spec import JudgeQuestion, JudgeSpec
from skillgate_ai.span_facts.asks import (
    _count_is_yes,
    _fact_kind,
    _predicate,
    _primary_file,
    _primary_tool,
)
from skillgate_ai.span_facts.patterns import _ANSWER_NO_IF
from skillgate_ai.span_facts.reply import (
    _compute_reply_fact,
    _connector_succeeded,
    _count_from_calls_log,
    _output_file,
    _parse_calls_log,
    _reply_hedges,
    _reply_text,
    _wanted_status,
)
from skillgate_ai.span_facts.tools import count_file_reads, count_tool_calls, tool_results


def resolve_log_facts(
    spec: JudgeSpec,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None = None,
    outputs: Sequence[Mapping[str, Any]] | str | None = None,
    skill_instructions: str | None = None,
) -> dict[str, Any]:
    """Answers for extras that are deterministic from the log. Empty → use the judge."""
    has_log = bool(spans) or bool(trajectory) or bool(outputs)
    if not has_log:
        return {}
    facts: dict[str, Any] = {}
    for question in spec.extras:
        computed = _compute_question(question, spans, trajectory=trajectory, outputs=outputs)
        if computed is not None:
            facts[question.id] = computed
    return _merge_wording_facts(
        spec,
        facts,
        spans,
        trajectory=trajectory,
        outputs=outputs,
        skill_instructions=skill_instructions,
    )


def apply_log_facts(
    spec: JudgeSpec,
    answers: Mapping[str, Any] | None,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None = None,
    outputs: Sequence[Mapping[str, Any]] | str | None = None,
    skill_instructions: str | None = None,
) -> dict[str, Any]:
    """Replace judge answers with log facts when the check can be computed."""
    merged = dict(answers or {})
    merged.update(
        resolve_log_facts(
            spec,
            spans,
            trajectory=trajectory,
            outputs=outputs,
            skill_instructions=skill_instructions,
        )
    )
    return merged


def _merge_wording_facts(
    spec: JudgeSpec,
    facts: dict[str, Any],
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None,
    outputs: Sequence[Mapping[str, Any]] | str | None,
    skill_instructions: str | None,
) -> dict[str, Any]:
    from skillgate_ai.wording_facts import resolve_wording_facts

    reply = _reply_text(outputs)
    wording = resolve_wording_facts(
        spec,
        outputs,
        skill_instructions,
        succeeded=_connector_succeeded(spans, trajectory, _parse_calls_log(outputs)),
        hedge=_reply_hedges(reply),
    )
    for qid, fact in wording.items():
        facts[qid] = fact
    return facts


def _compute_question(
    question: JudgeQuestion,
    spans: Sequence[Mapping[str, Any]] | None,
    *,
    trajectory: Mapping[str, Any] | None,
    outputs: Sequence[Mapping[str, Any]] | str | None = None,
) -> dict[str, Any] | None:
    if question.type != "predicate":
        return None
    ask = question.ask or ""
    kind = _fact_kind(ask)
    file_name = _primary_file(ask)
    tool = _primary_tool(ask, spans, trajectory=trajectory)
    if kind == "count":
        logged = _count_from_calls_log(ask, outputs)
        has_calls = bool(_output_file(outputs, "calls.log").strip())
        if has_calls and re.search(r"issue_refund", ask, re.IGNORECASE):
            count = logged
        elif file_name:
            count = count_file_reads(spans, file_name, trajectory=trajectory, tool=tool)
        elif tool:
            count = count_tool_calls(spans, tool, trajectory=trajectory)
        else:
            count = 0
        if count == 0 and not (spans or trajectory or has_calls):
            return None
        return _predicate(_count_is_yes(ask, count), source="log")
    if kind == "called":
        if not tool:
            return None
        count = count_tool_calls(spans, tool, trajectory=trajectory)
        called = count > 0
        if not called:
            return None
        never = bool(re.search(r"never called|did not call|didn't call", ask, re.IGNORECASE))
        if _ANSWER_NO_IF.search(ask) and not never:
            return _predicate(False, source="log")
        return _predicate(True, source="log")
    if kind == "return":
        if not tool:
            return None
        results = tool_results(spans, tool, trajectory=trajectory)
        if not results:
            return None
        blob = " ".join(results).lower()
        wanted = _wanted_status(ask)
        if not wanted:
            return None
        present = any(token in blob for token in wanted)
        if re.search(r"\bnot\s+" + re.escape(wanted[0]), ask, re.IGNORECASE):
            present = not present if "not" in ask.lower() else present
        if _ANSWER_NO_IF.search(ask) and re.search(
            r"\bnot\b.{0,40}" + re.escape(wanted[0]), ask, re.IGNORECASE
        ):
            return _predicate(any(token in blob for token in wanted), source="log")
        return _predicate(present, source="log")
    return _compute_reply_fact(ask, spans, trajectory=trajectory, outputs=outputs)


