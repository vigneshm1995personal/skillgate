"""Text form of the question payload the judge engine posts.

The UI and `skillgate checks show` both call this. Do not copy the wording elsewhere.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from skillgate_ai.errors import SkillGateError
from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    SOFT_CELL_LABELS,
    decisions_questions,
)
from skillgate_ai.judge_spec import JudgeQuestion, JudgeSpec, parse_extra_question


def render_judge_prompt(question: Mapping[str, Any]) -> str:
    """Render one decisions question exactly as the engine sends it."""
    instructions = str(question.get("instructions") or "").strip()
    lines: list[str] = []
    if instructions:
        lines.append(instructions)
    choices = question.get("choices") or []
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, Mapping):
                continue
            value = str(choice.get("value") or "").strip()
            description = str(choice.get("description") or "").strip()
            if value and description:
                lines.append(f"{value}: {description}")
            elif value:
                lines.append(value)
    levels = question.get("levels") or []
    if isinstance(levels, list) and levels:
        labels: list[str] = []
        for level in levels:
            if isinstance(level, Mapping):
                label = str(level.get("label") or "").strip()
            else:
                label = str(level).strip()
            if label:
                labels.append(label)
        if labels:
            lines.append("Levels: " + ", ".join(labels))
    return "\n".join(lines)


def builtin_prompt_rows() -> list[dict[str, Any]]:
    labels = {**CHECK_CELL_LABELS, **SOFT_CELL_LABELS}
    rows: list[dict[str, Any]] = []
    for question in decisions_questions():
        check_id = str(question["name"])
        rows.append(
            {
                "id": check_id,
                "sentence": labels.get(check_id) or str(question.get("instructions") or check_id),
                "prompt": render_judge_prompt(question),
                "builtin": True,
                "readonly": True,
            }
        )
    return rows


def prompt_for_id(
    check_id: str,
    *,
    spec: JudgeSpec | None = None,
    extras: Sequence[JudgeQuestion] | None = None,
) -> dict[str, Any]:
    for row in builtin_prompt_rows():
        if row["id"] == check_id:
            return row
    questions: Sequence[JudgeQuestion] = extras if extras is not None else ()
    if spec is not None:
        questions = spec.extras
    for question in questions:
        if question.id == check_id:
            return {
                "id": check_id,
                "sentence": question.ask,
                "prompt": render_judge_prompt(question.to_decisions()),
                "builtin": False,
                "readonly": False,
            }
    raise SkillGateError(f"No check named {check_id}.", exit_code=2)


def preview_extra(raw: Mapping[str, Any]) -> dict[str, Any]:
    question = parse_extra_question(raw)
    return prompt_for_id(question.id, extras=(question,))
