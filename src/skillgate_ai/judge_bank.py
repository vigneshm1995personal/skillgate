"""Fixed judge questions and Pass lock. No HTTP.

Shared with a future hosted TypeSafe wrapper so ordinals cannot drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

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
    "evidence_action_validity": frozenset(
        {"fully supported", "partially supported", "n/a"}
    ),
    "result_quality": frozenset({"clear and complete", "mostly good"}),
}

# 0.00–1.00, higher is better. This is the check outcome, not judge confidence.
CHOICE_SCORES: dict[str, dict[str, float]] = {
    "task_completion": {
        "fully completed": 1.0,
        "partially completed": 0.5,
        "not completed": 0.0,
    },
    "correctness": {
        "correct": 1.0,
        "mostly correct": 0.75,
        "insufficient evidence": 0.5,
        "incorrect": 0.0,
    },
    "instruction_adherence": {
        "fully followed": 1.0,
        "minor deviation": 0.75,
        "major deviation": 0.25,
        "violated": 0.0,
    },
    "evidence_action_validity": {
        "fully supported": 1.0,
        "partially supported": 0.75,
        "n/a": 1.0,
        "unsupported": 0.0,
    },
    "result_quality": {
        "clear and complete": 1.0,
        "mostly good": 0.75,
        "significant issues": 0.25,
        "poor": 0.0,
    },
    "path_efficiency": {
        "efficient": 1.0,
        "acceptable": 0.75,
        "looping": 0.25,
        "wasteful": 0.0,
    },
}

SOFT_PASS: frozenset[str] = frozenset({"efficient", "acceptable"})

PASS_NEED_LABEL: dict[str, str] = {
    "task_completion": "Fully completed",
    "correctness": "Correct or Mostly correct",
    "instruction_adherence": "Fully followed or Minor deviation",
    "evidence_action_validity": "Fully supported, Partially supported, or N/A",
    "result_quality": "Clear and complete or Mostly good",
}

EVIDENCE_RULE = (
    "Cite concrete evidence for this answer: a file path and line, or a command and its output. "
    "If that evidence shows no violation, answer not applicable or pass. "
    "Absence of a forbidden pattern is not a failure. "
    "Apply this rule the same way whenever you see the same evidence."
)

REFERENCE_EXAMPLE_NOTE = (
    "The reference (golden) is an example of an acceptable answer, not a full specification. "
    "Grade against the case prompt and the checks. "
    "Treat details in the example as required only when the case marks them required."
)


def with_evidence_rule(text: str) -> str:
    body = (text or "").strip()
    if "cite concrete evidence" in body.lower():
        return body
    if not body:
        return EVIDENCE_RULE
    return f"{body} {EVIDENCE_RULE}"


OUTCOME_SCORING_NOTES = (
    "Use workspace_files (collected output contents) and agent_trajectory.command_runs "
    "(commands plus captured stdout/stderr) as primary evidence. Do not claim tests or "
    "files were missing when they appear there. "
    f"{EVIDENCE_RULE} {REFERENCE_EXAMPLE_NOTE} "
    "Grade built-in checks against this test's expected outcome (expected_outcome, golden, "
    "contains), not a different success the user prompt might imply. If the expected "
    "outcome is an escalation or refusal — for example a refund is impossible, so the bot "
    "tells the customer and writes an owner report — doing that is Fully completed, not "
    "unfinished. "
    "When workspace_files show the expected deliverable (letter, spreadsheet, export, etc.) "
    "with correct substance and the listed SKILL.md rules show no violation, answer Fully "
    "followed for instruction_adherence. Use Minor deviation only when a listed rule was "
    "skipped in a small way. Do not hedge or split confidence between Fully followed and "
    "Minor deviation when no listed rule was broken. Style, tool choice, or cosmetic steps "
    "that are not listed rules are not a deviation. Major deviation fails the check. "
    "Use Fully supported / Partially supported for evidence_action_validity when outputs "
    "substantiate the result. "
    "instruction_adherence: Violated and Major deviation fail; only Minor deviation or Fully "
    "followed pass. "
    "task_completion: When SKILL.md requires refusing a shortcut, insisting on tests, or "
    "following a debug process instead of a quick fix, that behavior is Fully completed. "
    "When the task could not complete (pending, held for review, lookup required) and the "
    "customer reply honestly says the work is pending, not done, not submitted yet, has "
    "not gone through, or that no refund was issued / no refund went through, that is "
    "Correct, Fully followed, Fully completed, and a good result — never Incorrect, "
    "Violated, or Significant issues. Honest negation of a banned phrase (for example "
    "'has not been submitted', 'not issued', 'no refund') follows the rules; do not treat "
    "those sentences as Violated. A guarded single refund (a 409 lookup_required retry "
    "where only one refund went through) is the same: Correct and a good result. Write a "
    "short reason in your own words in the reason field for each built-in check (what you "
    "saw on this run). Do not paste a rubric definition."
)

OUTCOME_QUESTIONS: dict[str, dict[str, Any]] = {
    "task_completion": {
        "type": "choice",
        "instructions": "Got the job done?",
        "criteria": {
            "Fully completed": (
                "The test's expected outcome is fully met. If that expected outcome is an "
                "honest escalation or refusal (for example a refund is impossible, so the bot "
                "tells the customer and writes an owner report), doing that is Fully completed "
                "— not unfinished. Also Fully completed when the skill correctly followed "
                "SKILL.md by refusing a shortcut, requiring tests first, or enforcing a "
                "required process even when the user asked for something faster. An honest "
                "pending / not-done / no-refund reply when the work could not complete is "
                "Fully completed."
            ),
            "Partially completed": "Some of the requested work is done but incomplete.",
            "Not completed": "The requested work was not done.",
        },
    },
    "correctness": {
        "type": "choice",
        "instructions": "Got it right?",
        "criteria": {
            "Correct": (
                "The result matches the expected outcome. An honest customer reply that the "
                "work is pending, not done, not submitted yet, has not gone through, or that "
                "no refund was issued — when the task could not complete — is Correct."
            ),
            "Mostly correct": "Core claims are right with minor errors.",
            "Incorrect": (
                "The result is wrong. Do not choose Incorrect when the customer reply "
                "honestly says the work is pending, not done, not submitted, or that no "
                "refund went through."
            ),
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
                "Followed the listed SKILL.md rules and the user check. When those listed "
                "rules show no violation and the deterministic scorers passed, answer Fully "
                "followed with confidence 0.9 or higher. Refusing a shortcut or requiring "
                "tests when SKILL.md demands it counts as following. An honest pending / "
                "not-done / no-refund reply, including honest negation of banned wording "
                "('has not been submitted', 'not issued', 'no refund'), follows the rules."
            ),
            "Minor deviation": (
                "A listed SKILL.md rule was skipped in a small way that did not change the "
                "result. Do not use this when no listed rule was broken."
            ),
            "Major deviation": (
                "Material deviations from a listed SKILL.md rule or constraint that are not "
                "explained by a correct deliverable in workspace_files. Do not use when the "
                "work is fully done and no listed rule was broken."
            ),
            "Violated": (
                "Clear violations of the rules or constraints. Do not choose Violated for "
                "an honest negation of banned wording (pending, not done, not submitted, "
                "no refund)."
            ),
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
            "Clear and complete": (
                "The delivered result is clear and complete. An honest pending, not-done, "
                "held-for-review, guarded-single-refund, or no-refund reply is a good "
                "result when that is the true outcome."
            ),
            "Mostly good": "Mostly good with minor quality gaps (still Pass).",
            "Significant issues": (
                "Significant quality issues (Fail). Do not use this for an honest pending, "
                "held-for-review, guarded single-refund, or no-refund reply that correctly "
                "reports the outcome."
            ),
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
UNSURE_REVIEW = "unsure, needs review"
LOW_CONFIDENCE_WARNING = UNSURE_REVIEW
NO_REASON_RECORDED = "No reason recorded"
RUN_FACTS_LABEL = "run facts"
WHY_SUFFIX = "_why"
WORDING_OVERRIDE_NOTE = (
    "Wording check passed, so those Fail rows did not turn the gate red."
)
GUARD_REFUSED_RETRY_NOTE = (
    "A second refund attempt was refused. Only one refund went through."
)
MATCHED_OUTPUT_LINE = "Output matched what was expected."
CANNED_WHY_REASONS = frozenset(
    {
        "This run finished the customer request.",
        "This run left the customer request unfinished.",
        "This run did not attempt the customer request.",
        "The facts on this run are right.",
        "The facts on this run are wrong.",
        "The facts on this run only partly match.",
        "This run followed the skill's rules.",
        "This run broke a skill rule.",
        "No skill rule applied on this run.",
        "This run's tool use is allowed.",
        "This run's tool use is not allowed.",
        "This run needed no extra tool use.",
        "The customer reply on this run is clear.",
        "The customer reply on this run is not clear.",
        "This run's path was efficient.",
        "This run's path wasted steps.",
        "No short evidence line from this run.",
    }
)
DEFAULT_MIN_CONFIDENCE = 0.5
LOW_CONFIDENCE_MAX_ASKS = 3


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
    for key in ("choice", "value", "selected"):
        value = answer.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def extract_confidence(answer: Any) -> float | None:
    if not isinstance(answer, Mapping):
        return None
    raw = answer.get("confidence")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def extract_reason(answer: Any) -> str | None:
    if not isinstance(answer, Mapping):
        return None
    for key in (
        "reason",
        "rationale",
        "explanation",
        "why",
        "evidence",
        "justification",
        "reasoning",
    ):
        raw = answer.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def score_for_choice(key: str, choice: str | None) -> float | None:
    if not choice or not str(choice).strip():
        return None
    table = CHOICE_SCORES.get(key)
    if not table:
        return None
    return table.get(choice.strip().lower())


def choice_passed(key: str, choice: str | None) -> bool | None:
    text = (choice or "").strip().lower()
    if not text:
        return None
    lock = PASS_LOCK.get(key)
    if lock is not None:
        return text in lock
    if key in SOFT_CELL_ORDER or key == "path_efficiency":
        if text in SOFT_PASS:
            return True
        if text in CHOICE_SCORES.get("path_efficiency", {}):
            return False
        return None
    if text in {"yes", "pass", "true", "1"}:
        return True
    if text in {"no", "fail", "false", "0"}:
        return False
    return None


_DUMP_REASON_PREFIXES = (
    "Connector calls:",
    "The agent replied:",
    "Expected outcome:",
    "No short evidence",
)
_RUN_FACT_PREFIXES = (
    "Job result in the reply:",
    "Job expected:",
    "Facts in the reply:",
    "Facts expected:",
    "Listed skill rule:",
    "Reply checked against the rules:",
    "Tools used:",
    "Evidence in the reply:",
    "Customer-facing reply:",
    "Run path:",
)
_BUILT_REASON_PREFIXES = _DUMP_REASON_PREFIXES + _RUN_FACT_PREFIXES


def is_run_fact_reason(text: str | None) -> bool:
    """True for this-run evidence lines Skill Gate filled in (not judge prose)."""
    raw = str(text or "").strip()
    return bool(raw) and raw.startswith(_RUN_FACT_PREFIXES)


def is_built_reason(text: str | None) -> bool:
    """True for templates Skill Gate filled in, not a line the judge wrote."""
    raw = str(text or "").strip()
    if not raw:
        return False
    if raw in CANNED_WHY_REASONS or f"{raw.rstrip('.')}." in CANNED_WHY_REASONS:
        return True
    if raw.startswith(_BUILT_REASON_PREFIXES):
        return True
    return " on this run. Connector" in raw or " on this run. Reply:" in raw


def is_rubric_reason(key: str, choice: str | None, text: str | None) -> bool:
    if not text or not str(text).strip():
        return False
    rubric = criteria_text(key, choice)
    if not rubric:
        return False
    stored = str(text).strip()
    full = rubric.strip()
    if stored == full:
        return True
    return bool(len(stored) >= 20 and full.startswith(stored))


def answers_have_low_confidence(
    answers: Mapping[str, Any] | None,
    *,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    keys: tuple[str, ...] | list[str] | None = None,
) -> bool:
    """True when a blocking cell has a numeric confidence below the cutoff."""
    if not isinstance(answers, Mapping):
        return False
    for key in keys or CHECK_CELL_ORDER:
        confidence = extract_confidence(answers.get(key))
        if confidence is not None and confidence < min_confidence:
            return True
    return False


def majority_vote_answers(rounds: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Per-question majority. Ties break toward the higher-confidence answer."""
    usable = [dict(item) for item in rounds if isinstance(item, Mapping)]
    if not usable:
        return {}
    if len(usable) == 1:
        return dict(usable[0])
    keys: list[str] = []
    seen: set[str] = set()
    for blob in usable:
        for key in blob:
            name = str(key)
            if name not in seen:
                seen.add(name)
                keys.append(name)
    merged: dict[str, Any] = {}
    for key in keys:
        groups: dict[str, list[Any]] = {}
        for blob in usable:
            if key not in blob:
                continue
            answer = blob[key]
            groups.setdefault(_vote_token(answer), []).append(answer)
        if not groups:
            continue
        winner = max(groups.values(), key=_vote_rank)
        merged[key] = max(winner, key=_confidence_rank)
    return merged


def vote_round_summaries(rounds: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Choice and confidence per question for each ask."""
    out: list[dict[str, Any]] = []
    for blob in rounds:
        if not isinstance(blob, Mapping):
            continue
        round_map: dict[str, Any] = {}
        for key, answer in blob.items():
            entry: dict[str, Any] = {}
            choice = extract_choice(answer)
            if choice:
                entry["choice"] = choice
            confidence = extract_confidence(answer)
            if confidence is not None:
                entry["confidence"] = confidence
            if entry:
                round_map[str(key)] = entry
        if round_map:
            out.append(round_map)
    return out


def _vote_token(answer: Any) -> str:
    choice = extract_choice(answer)
    if choice:
        return f"choice:{choice.strip().lower()}"
    if isinstance(answer, Mapping):
        raw_prob = answer.get("probability")
        if isinstance(raw_prob, (int, float)) and not isinstance(raw_prob, bool):
            return "yes" if float(raw_prob) >= 0.8 else "no"
        if answer.get("score") is not None:
            return f"score:{answer.get('score')}"
    return repr(answer)


def _confidence_rank(answer: Any) -> float:
    confidence = extract_confidence(answer)
    return confidence if confidence is not None else -1.0


def _vote_rank(group: list[Any]) -> tuple[int, float]:
    return (len(group), max((_confidence_rank(item) for item in group), default=-1.0))


def extract_probabilities(answer: Any) -> list[dict[str, Any]] | None:
    if not isinstance(answer, Mapping):
        return None
    raw = answer.get("probabilities")
    rows: list[dict[str, Any]] = []
    if isinstance(raw, Mapping):
        for value, probability in raw.items():
            row: dict[str, Any] = {}
            if value is not None:
                row["value"] = value
            if isinstance(probability, (int, float)) and not isinstance(probability, bool):
                row["probability"] = float(probability)
            if row:
                rows.append(row)
        return rows or None
    if not isinstance(raw, list):
        return None
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        value = item.get("value")
        probability = item.get("probability")
        row = {}
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
            reasons.append(
                f"{CHECK_CELL_LABELS[key]} {display} (need {PASS_NEED_LABEL[key]})"
            )
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
