"""Fixed judge questions and Pass lock. No HTTP.

Shared with a future hosted TypeSafe wrapper so ordinals cannot drift.
"""

from __future__ import annotations

from typing import Any, Mapping

CHECK_CELL_ORDER: tuple[str, ...] = (
    "task_completion",
    "correctness",
    "instruction_adherence",
    "evidence_action_validity",
    "result_quality",
)

CHECK_CELL_LABELS: dict[str, str] = {
    "task_completion": "Got the job done?",
    "correctness": "Got it right?",
    "instruction_adherence": "Followed the rules?",
    "evidence_action_validity": "Used the right evidence/actions?",
    "result_quality": "Delivered a good result?",
}

SOFT_CELL_ORDER: tuple[str, ...] = ("path_efficiency",)

SOFT_CELL_LABELS: dict[str, str] = {
    "path_efficiency": "How it ran",
}

PATH_NOT_AVAILABLE = "Not available. No recorded path."

PASS_LOCK: dict[str, frozenset[str]] = {
    "task_completion": frozenset({"fully completed"}),
    "correctness": frozenset({"correct", "mostly correct"}),
    "instruction_adherence": frozenset({"fully followed", "minor deviation"}),
    "evidence_action_validity": frozenset({"fully supported", "n/a"}),
    "result_quality": frozenset({"clear and complete", "mostly good"}),
}

PASS_NEED_LABEL: dict[str, str] = {
    "task_completion": "Fully completed",
    "correctness": "Correct or Mostly correct",
    "instruction_adherence": "Fully followed or Minor deviation",
    "evidence_action_validity": "Fully supported or N/A",
    "result_quality": "Clear and complete or Mostly good",
}

OUTCOME_SCORING_NOTES = (
    "Use workspace_files (collected output contents) and agent_trajectory.command_runs "
    "(commands plus captured stdout/stderr) as primary evidence. Do not claim tests or "
    "files were missing when they appear there. "
    "instruction_adherence: Minor deviation passes; only Major deviation or Violated fails. "
    "task_completion: When SKILL.md requires refusing a shortcut, insisting on tests, or "
    "following a debug process instead of a quick fix, that behavior is Fully completed."
)

OUTCOME_QUESTIONS: dict[str, dict[str, Any]] = {
    "task_completion": {
        "type": "choice",
        "instructions": "Got the job done?",
        "criteria": {
            "Fully completed": (
                "The requested work is fully done, OR the skill correctly followed SKILL.md "
                "by refusing a shortcut, requiring tests first, or enforcing a required process "
                "even when the user asked for something faster."
            ),
            "Partially completed": "Some of the requested work is done but incomplete.",
            "Not completed": "The requested work was not done.",
        },
    },
    "correctness": {
        "type": "choice",
        "instructions": "Got it right?",
        "criteria": {
            "Correct": "The result matches the expected outcome.",
            "Mostly correct": "Core claims are right with minor errors.",
            "Incorrect": "The result is wrong.",
            "Insufficient evidence": (
                "Not enough evidence in workspace_files, command_runs, or transcript to judge."
            ),
        },
    },
    "instruction_adherence": {
        "type": "choice",
        "instructions": "Followed the rules?",
        "criteria": {
            "Fully followed": (
                "Followed the user check and the skill's SKILL.md instructions fully. "
                "Refusing a shortcut or requiring tests when SKILL.md demands it counts as following."
            ),
            "Minor deviation": "Small deviations that did not undermine the result.",
            "Major deviation": "Material deviations from the instructions.",
            "Violated": "Clear violations of the rules or constraints.",
        },
    },
    "evidence_action_validity": {
        "type": "choice",
        "instructions": "Used the right evidence/actions?",
        "criteria": {
            "Fully supported": (
                "Claims and actions are backed by transcript, agent_trajectory, or tool output."
            ),
            "Partially supported": "Some claims or actions lack support.",
            "Unsupported": "Key claims or actions are unsupported.",
            "N/A": "No evidence/actions were required for this check.",
        },
    },
    "result_quality": {
        "type": "choice",
        "instructions": "Delivered a good result?",
        "criteria": {
            "Clear and complete": "The delivered result is clear and complete.",
            "Mostly good": "Mostly good with minor quality gaps (still Pass).",
            "Significant issues": "Significant quality issues (Fail).",
            "Poor": "Poor quality result (Fail).",
        },
    },
}

SOFT_OUTCOME_QUESTIONS: dict[str, dict[str, Any]] = {
    "path_efficiency": {
        "type": "choice",
        "instructions": (
            "How efficient was the path? Judge looping, thrashing, or wasted "
            "tool calls from the transcript. A short step count is not Efficient "
            "if the transcript shows looping. This must not decide whether the "
            "job was done. Pick exactly one."
        ),
        "criteria": {
            "Efficient": (
                "The skill took a direct path: no repeated tool calls, no loops, no wasted steps."
            ),
            "Acceptable": "The skill finished with only minor extra steps and no looping.",
            "Looping": (
                "The skill repeated the same or near-same tool calls without making progress."
            ),
            "Wasteful": "The skill spent many tool calls off-task or thrashing.",
        },
    },
}

UNUSABLE_ANSWER = "The judge returned an unusable answer."
LOW_CONFIDENCE_WARNING = "The judge wasn't very sure about this one."
DEFAULT_MIN_CONFIDENCE = 0.5


def all_questions() -> dict[str, dict[str, Any]]:
    merged = dict(OUTCOME_QUESTIONS)
    merged.update(SOFT_OUTCOME_QUESTIONS)
    return merged


def criteria_keys(key: str) -> tuple[str, ...]:
    spec = all_questions().get(key) or {}
    criteria = spec.get("criteria") or {}
    return tuple(str(name) for name in criteria)


def criteria_text(key: str, choice: str | None) -> str | None:
    if not choice or not str(choice).strip():
        return None
    spec = all_questions().get(key) or {}
    criteria = spec.get("criteria")
    if not isinstance(criteria, Mapping):
        return None
    text = criteria.get(choice)
    if isinstance(text, str) and text.strip():
        return text.strip()
    lower = choice.strip().lower()
    for name, value in criteria.items():
        if (
            isinstance(name, str)
            and name.lower() == lower
            and isinstance(value, str)
            and value.strip()
        ):
            return value.strip()
    return None


def canonical_choice(key: str, choice: str | None) -> str | None:
    """Return the bank's original casing, or None if not an allowed enum."""
    if not isinstance(choice, str) or not choice.strip():
        return None
    lower = choice.strip().lower()
    for name in criteria_keys(key):
        if name.lower() == lower:
            return name
    return None


def extract_choice(answer: Any) -> str | None:
    if isinstance(answer, str):
        return answer.strip() or None
    if not isinstance(answer, Mapping):
        return None
    value = answer.get("choice")
    return value.strip() if isinstance(value, str) and value.strip() else None


def extract_confidence(answer: Any) -> float | None:
    if not isinstance(answer, Mapping):
        return None
    raw = answer.get("confidence")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def extract_probabilities(answer: Any) -> list[dict[str, Any]] | None:
    if not isinstance(answer, Mapping):
        return None
    raw = answer.get("probabilities")
    if not isinstance(raw, list):
        return None
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        value = item.get("value")
        probability = item.get("probability")
        row: dict[str, Any] = {}
        if value is not None:
            row["value"] = value
        if isinstance(probability, (int, float)) and not isinstance(probability, bool):
            row["probability"] = float(probability)
        label = item.get("label")
        if isinstance(label, str) and label.strip():
            row["label"] = label
        if row:
            rows.append(row)
    return rows


def unusable_answers(answers: Mapping[str, Any] | None) -> bool:
    """True when a Pass-lock cell is missing or not a bank enum.

    Path is soft: missing is fine; a present invalid enum still fails closed.
    """
    if not isinstance(answers, Mapping):
        return True
    for key in CHECK_CELL_ORDER:
        if canonical_choice(key, extract_choice(answers.get(key))) is None:
            return True
    for key in SOFT_CELL_ORDER:
        if key not in answers:
            continue
        if canonical_choice(key, extract_choice(answers.get(key))) is None:
            return True
    return False


def outcome_verdict(answers: Mapping[str, Any] | None) -> tuple[bool, list[str]]:
    """Pass lock. Invalid/missing enums fail closed."""
    if unusable_answers(answers):
        return False, [UNUSABLE_ANSWER]
    assert isinstance(answers, Mapping)
    reasons: list[str] = []
    for key in CHECK_CELL_ORDER:
        raw_choice = extract_choice(answers.get(key))
        canonical = canonical_choice(key, raw_choice) or ""
        if canonical.strip().lower() not in PASS_LOCK[key]:
            display = canonical or (raw_choice or "unclear")
            reason = f"{CHECK_CELL_LABELS[key]} {display} (need {PASS_NEED_LABEL[key]})"
            extra = criteria_text(key, display)
            if extra:
                reason += f" — {extra}"
            reasons.append(reason)
    return (not reasons), reasons


def low_confidence_warnings(
    answers: Mapping[str, Any] | None,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    expect_confidence: bool = True,
) -> list[str]:
    """Warnings only. Never changes Pass/Fail. Decisions backend only."""
    if not expect_confidence or not isinstance(answers, Mapping):
        return []
    passed, _ = outcome_verdict(answers)
    if not passed:
        return []
    for key in CHECK_CELL_ORDER:
        canonical = canonical_choice(key, extract_choice(answers.get(key)))
        if canonical is None or canonical.strip().lower() not in PASS_LOCK[key]:
            continue
        confidence = extract_confidence(answers.get(key))
        if confidence is None or confidence < min_confidence:
            return [LOW_CONFIDENCE_WARNING]
    return []


def decisions_questions(*, include_path: bool = True) -> list[dict[str, Any]]:
    questions: list[dict[str, Any]] = []
    for key, spec in all_questions().items():
        if not include_path and key in SOFT_CELL_ORDER:
            continue
        criteria = spec.get("criteria") or {}
        label = spec.get("instructions") or CHECK_CELL_LABELS.get(key) or key
        instructions = str(label)
        if key in CHECK_CELL_ORDER and "Pick exactly one." not in instructions:
            instructions = f"{instructions.rstrip()} Pick exactly one."
        questions.append(
            {
                "type": "choice",
                "name": key,
                "instructions": instructions,
                "choices": [
                    {"value": name, "description": text}
                    for name, text in criteria.items()
                ],
            }
        )
    return questions


def structured_output_schema(*, include_path: bool = True) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for key, spec in all_questions().items():
        if not include_path and key in SOFT_CELL_ORDER:
            continue
        properties[key] = {
            "type": "string",
            "enum": list(criteria_keys(key)),
            "description": spec.get("instructions") or key,
        }
        required.append(key)
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
