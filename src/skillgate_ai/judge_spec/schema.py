"""Resolve built-in + extra judge questions. No HTTP."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from skillgate_ai.judge_bank import decisions_questions, structured_output_schema
from skillgate_ai.judge_spec.model import JudgeQuestion, JudgeSpec
from skillgate_ai.judge_spec.parse import _extra_list


def spec_decisions_questions(spec: JudgeSpec, *, include_path: bool = True) -> list[dict[str, Any]]:
    questions = decisions_questions(include_path=include_path)
    for question in spec.extras:
        if question.include_when == "path_recorded" and not include_path:
            continue
        questions.append(question.to_decisions())
    return questions


def spec_structured_schema(spec: JudgeSpec, *, include_path: bool = True) -> dict[str, Any]:
    schema = structured_output_schema(include_path=include_path)
    properties = dict(schema.get("properties") or {})
    required = list(schema.get("required") or [])
    for question in spec.extras:
        if question.include_when == "path_recorded" and not include_path:
            continue
        properties[question.id] = _extra_schema_property(question)
        required.append(question.id)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def judge_block_to_dict(block: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(block, Mapping):
        return None
    extra = list(_extra_list(block.get("extra_questions")))
    on_fail = block.get("on_fail") if isinstance(block.get("on_fail"), Mapping) else None
    payload: dict[str, Any] = {}
    if extra:
        payload["extra_questions"] = extra
    if on_fail:
        payload["on_fail"] = dict(on_fail)
    if block.get("min_confidence") is not None:
        payload["min_confidence"] = block.get("min_confidence")
    if block.get("score_no_trigger"):
        payload["score_no_trigger"] = True
    return payload or None


def _extra_schema_property(question: JudgeQuestion) -> dict[str, Any]:
    if question.type == "predicate":
        return {"type": "number", "minimum": 0, "maximum": 1, "description": question.ask}
    if question.type == "score":
        if question.levels:
            return {"type": "string", "enum": list(question.levels), "description": question.ask}
        return {"type": "number", "description": question.ask}
    values = [str(row.get("value")) for row in question.choices if row.get("value") is not None]
    if values:
        return {"type": "string", "enum": values, "description": question.ask}
    return {"type": "string", "description": question.ask}
