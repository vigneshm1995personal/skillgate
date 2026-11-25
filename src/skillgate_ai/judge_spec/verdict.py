"""Resolve built-in + extra judge questions. No HTTP."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, overload

from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    CHECK_CELL_ORDER,
    LOW_CONFIDENCE_WARNING,
    PASS_LOCK,
    SOFT_CELL_ORDER,
    UNUSABLE_ANSWER,
    canonical_choice,
    extract_choice,
    extract_confidence,
    outcome_verdict,
)
from skillgate_ai.judge_spec.model import JudgeQuestion, JudgeSpec


def spec_verdict(
    spec: JudgeSpec,
    answers: Mapping[str, Any] | None,
    *,
    supports_confidence: bool = False,
    include_path: bool = True,
    skipped: Sequence[str] | None = None,
) -> tuple[bool, list[str], list[str]]:
    if not isinstance(answers, Mapping):
        answers = {}
    skipped_ids = {str(item) for item in (skipped or []) if str(item).strip()}
    blocking = [q for q in spec.questions if q.builtin and q.id in CHECK_CELL_ORDER]
    builtin_lock = {q.id: q for q in blocking}
    passed_lock, lock_reasons = outcome_verdict({key: answers.get(key) for key in CHECK_CELL_ORDER})
    reasons: list[str] = []
    warnings: list[str] = []
    failed = False
    unsure = False
    if not passed_lock:
        for reason in lock_reasons:
            key = _reason_key(reason)
            question = builtin_lock.get(key) if key else None
            if question is not None and question.on_fail == "warn":
                warnings.append(reason)
                continue
            conf = extract_confidence(answers.get(key)) if key else None
            if supports_confidence and conf is not None and conf < spec.min_confidence:
                unsure = True
                continue
            failed = True
            reasons.append(reason)
    for question in spec.questions:
        if question.id in skipped_ids:
            continue
        if question.builtin and question.id in CHECK_CELL_ORDER:
            continue
        if question.include_when == "path_recorded" and not include_path:
            continue
        if question.builtin and question.id in SOFT_CELL_ORDER and not include_path:
            continue
        ok, detail = extra_question_passed(question, answers.get(question.id))
        if ok or not detail:
            continue
        if question.on_fail == "warn":
            warnings.append(detail)
        else:
            failed = True
            reasons.append(detail)
    if not failed and supports_confidence:
        low = low_confidence_for_spec(spec, answers, min_confidence=spec.min_confidence)
        if low:
            unsure = True
    if unsure:
        warnings.append(LOW_CONFIDENCE_WARNING)
    return (not failed), reasons, warnings


def extra_block_failure_map(
    spec: JudgeSpec,
    answers: Mapping[str, Any] | None,
    *,
    skipped: Sequence[str] | None = None,
) -> dict[str, str]:
    blob = answers if isinstance(answers, Mapping) else {}
    skip = {str(item) for item in (skipped or []) if str(item).strip()}
    failures: dict[str, str] = {}
    for question in spec.extras:
        if question.id in skip or question.on_fail != "block":
            continue
        ok, detail = extra_question_passed(question, blob.get(question.id))
        if not ok and detail:
            failures[question.id] = detail
    return failures


def extra_block_failures(
    spec: JudgeSpec,
    answers: Mapping[str, Any] | None,
    *,
    skipped: Sequence[str] | None = None,
) -> list[str]:
    return list(extra_block_failure_map(spec, answers, skipped=skipped).values())


_NOT_APPLICABLE = frozenset({"not applicable", "n/a", "na", "not_applicable"})


def _is_not_applicable(answer: Any) -> bool:
    texts: list[str] = []
    if isinstance(answer, str):
        texts.append(answer)
    elif isinstance(answer, Mapping):
        for key in ("choice", "score", "label", "value"):
            value = answer.get(key)
            if isinstance(value, str):
                texts.append(value)
    return any(text.strip().lower() in _NOT_APPLICABLE for text in texts)


def extra_question_passed(question: JudgeQuestion, answer: Any) -> tuple[bool, str | None]:
    if _is_not_applicable(answer):
        return True, None
    if question.builtin and question.id in SOFT_CELL_ORDER:
        if answer is None:
            return True, None
        choice = canonical_choice(question.id, extract_choice(answer))
        if choice is None and extract_choice(answer):
            return False, UNUSABLE_ANSWER
        return True, None
    if question.type == "predicate":
        probability = _extract_probability(answer)
        if probability is None:
            return _unusable_or_fail(question)
        threshold = _gte(question.pass_if, default=0.8)
        if probability >= threshold:
            return True, None
        named = ""
        if isinstance(answer, Mapping):
            named = str(answer.get("reason") or "").strip()
        return False, named or f"{question.ask} No"
    if question.type == "score":
        score = _extract_score(answer)
        if score is None:
            return _unusable_or_fail(question)
        score_threshold: float | None = _gte(question.pass_if, default=None)
        if score_threshold is not None and float(score) < score_threshold:
            return False, f"{question.ask} {score}"
        if question.levels:
            pass_levels = _pass_levels(question)
            label = str(score)
            if pass_levels and label not in pass_levels:
                return False, f"{question.ask} {label}"
        return True, None
    choice = _extract_choice_value(answer)
    if not choice:
        return _unusable_or_fail(question)
    allowed = {str(row.get("value")): bool(row.get("pass")) for row in question.choices}
    if (
        question.choices
        and choice not in allowed
        and choice.lower() not in {name.lower() for name in allowed}
    ):
        return _unusable_or_fail(question)
    passed = _choice_passes(question, choice)
    if passed:
        return True, None
    return False, f"{question.ask} {choice}"


def low_confidence_for_spec(
    spec: JudgeSpec,
    answers: Mapping[str, Any],
    *,
    min_confidence: float,
) -> list[str]:
    for question in spec.questions:
        if question.on_fail != "block":
            continue
        if question.type in {"predicate", "score"}:
            continue
        if question.builtin and question.id in CHECK_CELL_ORDER:
            canonical = canonical_choice(question.id, extract_choice(answers.get(question.id)))
            if canonical is None or canonical.strip().lower() not in PASS_LOCK[question.id]:
                continue
        else:
            ok, _ = extra_question_passed(question, answers.get(question.id))
            if not ok:
                continue
        confidence = extract_confidence(answers.get(question.id))
        if confidence is None or confidence < min_confidence:
            return [LOW_CONFIDENCE_WARNING]
    return []


@overload
def _gte(pass_if: Mapping[str, Any] | None, *, default: float) -> float: ...


@overload
def _gte(pass_if: Mapping[str, Any] | None, *, default: None) -> float | None: ...


def _gte(pass_if: Mapping[str, Any] | None, *, default: float | None) -> float | None:
    if not isinstance(pass_if, Mapping) or "gte" not in pass_if:
        return default
    try:
        return float(pass_if["gte"])
    except (TypeError, ValueError):
        return default


def coerce_extra_answer(raw: Any, *, kind: str | None = None) -> Any:
    """Turn a schema scalar into the mapping shape Decisions answers use."""
    if isinstance(raw, Mapping):
        if kind != "predicate":
            return raw
        probability = _extract_probability(raw)
        if probability is None or "probability" in raw:
            return raw
        lifted = dict(raw)
        lifted["probability"] = probability
        return lifted
    if isinstance(raw, str) and raw.strip():
        return {"choice": raw.strip()}
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if kind == "score":
            return {"score": float(raw)}
        return {"probability": float(raw)}
    return raw


def _extract_probability(answer: Any) -> float | None:
    """Yes-probability from a predicate answer.

    Decision models return this as ``probability``, as ``noul``
    (the probability of yes), or as a yes/no choice.
    """
    if isinstance(answer, bool):
        return 1.0 if answer else 0.0
    if isinstance(answer, (int, float)):
        return float(answer)
    if not isinstance(answer, Mapping):
        return None
    for key in ("probability", "noul"):
        raw = answer.get(key)
        if isinstance(raw, bool):
            return 1.0 if raw else 0.0
        if isinstance(raw, (int, float)):
            return float(raw)
    choice = extract_choice(answer)
    if isinstance(choice, str):
        lower = choice.strip().lower()
        if lower in {"yes", "true"}:
            return 1.0
        if lower in {"no", "false"}:
            return 0.0
    return None


def _extract_score(answer: Any) -> Any:
    if isinstance(answer, (int, float, str)) and not isinstance(answer, bool):
        return answer
    if not isinstance(answer, Mapping):
        return None
    if "score" in answer:
        return answer.get("score")
    return extract_choice(answer)


def _extract_choice_value(answer: Any) -> str | None:
    if isinstance(answer, str) and answer.strip():
        return answer.strip()
    return extract_choice(answer)


def _choice_passes(question: JudgeQuestion, choice: str) -> bool:
    lower = choice.strip().lower()
    for row in question.choices:
        value = str(row.get("value") or "")
        if value == choice or value.lower() == lower:
            return bool(row.get("pass"))
    return False


def _pass_levels(question: JudgeQuestion) -> set[str]:
    raw = (question.pass_if or {}).get("in") if question.pass_if else None
    if isinstance(raw, list):
        return {str(item) for item in raw}
    return set()


def _unusable_or_fail(question: JudgeQuestion) -> tuple[bool, str]:
    return False, UNUSABLE_ANSWER if question.builtin else f"{question.ask} (no answer)"


def _reason_key(reason: str) -> str | None:
    for key, label in CHECK_CELL_LABELS.items():
        if reason.startswith(label):
            return key
    return None
