"""Resolve built-in + extra judge questions. No HTTP."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Any, Mapping, Sequence

from skillgate_ai.errors import SuiteError
from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    CHECK_CELL_ORDER,
    DEFAULT_MIN_CONFIDENCE,
    LOW_CONFIDENCE_WARNING,
    PASS_LOCK,
    SOFT_CELL_LABELS,
    SOFT_CELL_ORDER,
    UNUSABLE_ANSWER,
    canonical_choice,
    decisions_questions,
    extract_choice,
    extract_confidence,
    outcome_verdict,
    structured_output_schema,
)

MAX_QUESTIONS = 20
MAX_EXTRAS = MAX_QUESTIONS - len(CHECK_CELL_ORDER) - len(SOFT_CELL_ORDER)
RESERVED_IDS = frozenset(CHECK_CELL_ORDER) | frozenset(SOFT_CELL_ORDER)
QUESTION_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TYPE_ALIASES = {
    "predicate": "predicate",
    "yes/no": "predicate",
    "yesno": "predicate",
    "choice": "choice",
    "pick one": "choice",
    "pick_one": "choice",
    "score": "score",
}

RESERVED_ID_MESSAGE = (
    "`{id}` is a Skill Gate question. Add a new id, or change Fail vs warn for the built-in."
)
CAP_MESSAGE = "A check can ask at most 20 scoring questions (Skill Gate’s 6 plus yours)."
TYPE_MESSAGE = "Question {id}: type must be Yes/No, pick one, or score."


@dataclass(frozen=True)
class JudgeQuestion:
    id: str
    type: str
    ask: str
    on_fail: str = "block"
    builtin: bool = False
    choices: tuple[dict[str, Any], ...] = ()
    levels: tuple[str, ...] = ()
    pass_if: dict[str, Any] | None = None
    include_when: str | None = None

    @property
    def label(self) -> str:
        if self.builtin and self.id in CHECK_CELL_LABELS:
            return CHECK_CELL_LABELS[self.id]
        if self.builtin and self.id in SOFT_CELL_LABELS:
            return SOFT_CELL_LABELS[self.id]
        return self.ask

    def to_decisions(self) -> dict[str, Any]:
        if self.type == "predicate":
            return {"type": "predicate", "name": self.id, "instructions": self.ask}
        if self.type == "score":
            labels = list(self.levels) or ["1", "2", "3", "4", "5"]
            return {
                "type": "score",
                "name": self.id,
                "instructions": self.ask,
                "levels": [{"label": label} for label in labels],
            }
        choices = []
        for row in self.choices:
            item = {"value": row.get("value")}
            if row.get("description"):
                item["description"] = row["description"]
            choices.append(item)
        return {
            "type": "choice",
            "name": self.id,
            "instructions": self.ask,
            "choices": choices,
        }


@dataclass(frozen=True)
class JudgeSpec:
    questions: tuple[JudgeQuestion, ...]
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    score_no_trigger: bool = False

    @property
    def extras(self) -> tuple[JudgeQuestion, ...]:
        return tuple(q for q in self.questions if not q.builtin)

    @property
    def builtins(self) -> tuple[JudgeQuestion, ...]:
        return tuple(q for q in self.questions if q.builtin)

    def with_questions(self, questions: list[JudgeQuestion]) -> JudgeSpec:
        return replace(self, questions=tuple(questions))


def builtin_questions(*, on_fail: Mapping[str, str] | None = None) -> list[JudgeQuestion]:
    overrides = on_fail or {}
    rows: list[JudgeQuestion] = []
    for key in CHECK_CELL_ORDER:
        rows.append(
            JudgeQuestion(
                id=key,
                type="choice",
                ask=CHECK_CELL_LABELS[key],
                on_fail=_on_fail_value(overrides.get(key), default="block"),
                builtin=True,
            )
        )
    for key in SOFT_CELL_ORDER:
        rows.append(
            JudgeQuestion(
                id=key,
                type="choice",
                ask=SOFT_CELL_LABELS[key],
                on_fail=_on_fail_value(overrides.get(key), default="warn"),
                builtin=True,
            )
        )
    return rows


def builtin_spec(
    *,
    on_fail: Mapping[str, str] | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    score_no_trigger: bool = False,
) -> JudgeSpec:
    return JudgeSpec(
        questions=tuple(builtin_questions(on_fail=on_fail)),
        min_confidence=min_confidence,
        score_no_trigger=score_no_trigger,
    )


def resolve_judge_spec(
    *,
    project: Mapping[str, Any] | None = None,
    pack: Mapping[str, Any] | None = None,
    case: Mapping[str, Any] | None = None,
) -> JudgeSpec:
    layers = [layer for layer in (project, pack, case) if isinstance(layer, Mapping)]
    on_fail: dict[str, str] = {}
    min_confidence = DEFAULT_MIN_CONFIDENCE
    score_no_trigger = False
    extras: list[JudgeQuestion] = []
    seen: set[str] = set(RESERVED_IDS)
    for layer in layers:
        raw_on_fail = layer.get("on_fail")
        if isinstance(raw_on_fail, Mapping):
            for key, value in raw_on_fail.items():
                name = str(key).strip()
                if name not in RESERVED_IDS:
                    raise SuiteError(
                        RESERVED_ID_MESSAGE.format(id=name)
                        if name
                        else "on_fail keys must be Skill Gate question ids."
                    )
                on_fail[name] = _on_fail_value(value, default="block")
        if "min_confidence" in layer and layer.get("min_confidence") is not None:
            try:
                min_confidence = float(layer.get("min_confidence"))
            except (TypeError, ValueError) as exc:
                raise SuiteError("min_confidence must be a number.") from exc
        if layer.get("score_no_trigger") is True:
            score_no_trigger = True
        for raw in _extra_list(layer.get("extra_questions")):
            question = parse_extra_question(raw)
            if question.id in RESERVED_IDS:
                raise SuiteError(RESERVED_ID_MESSAGE.format(id=question.id), exit_code=2)
            if question.id in seen:
                raise SuiteError(
                    f"`{question.id}` is already a scoring question. Pick a new id.",
                    exit_code=2,
                )
            seen.add(question.id)
            extras.append(question)
    questions = builtin_questions(on_fail=on_fail) + extras
    if len(questions) > MAX_QUESTIONS:
        raise SuiteError(CAP_MESSAGE, exit_code=2)
    return JudgeSpec(
        questions=tuple(questions),
        min_confidence=min_confidence,
        score_no_trigger=score_no_trigger,
    )


def parse_extra_question(raw: Mapping[str, Any] | Any) -> JudgeQuestion:
    if not isinstance(raw, Mapping):
        raise SuiteError("Each extra question must be a mapping.", exit_code=2)
    qid = str(raw.get("id") or "").strip()
    if not qid or not QUESTION_ID_RE.match(qid) or len(qid) > 64:
        raise SuiteError(
            "Extra question id must be lowercase letters, digits, and underscores (max 64).",
            exit_code=2,
        )
    if qid in RESERVED_IDS:
        raise SuiteError(RESERVED_ID_MESSAGE.format(id=qid), exit_code=2)
    kind = TYPE_ALIASES.get(str(raw.get("type") or "").strip().lower())
    if kind is None:
        raise SuiteError(TYPE_MESSAGE.format(id=qid), exit_code=2)
    ask = str(raw.get("ask") or raw.get("instructions") or "").strip()
    if not ask:
        raise SuiteError(f"Question {qid}: add the ask text.", exit_code=2)
    choices = _parse_choices(raw.get("choices"), qid=qid, kind=kind)
    levels = _parse_levels(raw.get("levels"), qid=qid, kind=kind)
    pass_if = raw.get("pass_if") if isinstance(raw.get("pass_if"), Mapping) else None
    include_when = str(raw.get("include_when") or "").strip() or None
    return JudgeQuestion(
        id=qid,
        type=kind,
        ask=ask,
        on_fail=_on_fail_value(raw.get("on_fail"), default="block"),
        builtin=False,
        choices=choices,
        levels=levels,
        pass_if=dict(pass_if) if pass_if else None,
        include_when=include_when,
    )


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
    passed_lock, lock_reasons = outcome_verdict(
        {key: answers.get(key) for key in CHECK_CELL_ORDER}
    )
    reasons: list[str] = []
    warnings: list[str] = []
    failed = False
    if not passed_lock:
        for reason in lock_reasons:
            key = _reason_key(reason)
            question = builtin_lock.get(key) if key else None
            if question is not None and question.on_fail == "warn":
                warnings.append(reason)
            else:
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
        warnings.extend(
            low_confidence_for_spec(spec, answers, min_confidence=spec.min_confidence)
        )
    return (not failed), reasons, warnings


def extra_block_failures(
    spec: JudgeSpec,
    answers: Mapping[str, Any] | None,
    *,
    skipped: Sequence[str] | None = None,
) -> list[str]:
    blob = answers if isinstance(answers, Mapping) else {}
    skip = {str(item) for item in (skipped or []) if str(item).strip()}
    failures: list[str] = []
    for question in spec.extras:
        if question.id in skip or question.on_fail != "block":
            continue
        ok, detail = extra_question_passed(question, blob.get(question.id))
        if not ok and detail:
            failures.append(detail)
    return failures


def extra_question_passed(question: JudgeQuestion, answer: Any) -> tuple[bool, str | None]:
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
        return False, f"{question.ask} No"
    if question.type == "score":
        score = _extract_score(answer)
        if score is None:
            return _unusable_or_fail(question)
        threshold = _gte(question.pass_if, default=None)
        if threshold is not None and float(score) < threshold:
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
    if question.choices and choice not in allowed and choice.lower() not in {
        name.lower() for name in allowed
    }:
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


def _extra_list(raw: Any) -> list[Mapping[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SuiteError("extra_questions must be a list.", exit_code=2)
    return [item for item in raw if item is not None]


def _on_fail_value(value: Any, *, default: str) -> str:
    if value is None or str(value).strip() == "":
        return default
    raw = str(value).strip().lower()
    if raw in {"block", "fail", "fail the check"}:
        return "block"
    if raw in {"warn", "warn only", "warning"}:
        return "warn"
    raise SuiteError("on_fail must be Fail the check or Warn only.", exit_code=2)


def _parse_choices(raw: Any, *, qid: str, kind: str) -> tuple[dict[str, Any], ...]:
    if kind != "choice":
        return ()
    if not isinstance(raw, list) or len(raw) < 2:
        raise SuiteError(f"Question {qid}: pick-one questions need at least two choices.", exit_code=2)
    rows: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            rows.append({"value": item, "pass": False})
            continue
        if not isinstance(item, Mapping) or not str(item.get("value") or "").strip():
            raise SuiteError(f"Question {qid}: each choice needs a value.", exit_code=2)
        rows.append(
            {
                "value": str(item.get("value")).strip(),
                "description": str(item.get("description") or "").strip(),
                "pass": bool(item.get("pass")),
            }
        )
    if not any(row.get("pass") for row in rows):
        rows[0]["pass"] = True
    return tuple(rows)


def _parse_levels(raw: Any, *, qid: str, kind: str) -> tuple[str, ...]:
    if kind != "score":
        return ()
    if raw is None:
        return ()
    if not isinstance(raw, list) or len(raw) < 2:
        raise SuiteError(f"Question {qid}: score questions need at least two levels.", exit_code=2)
    return tuple(str(item).strip() for item in raw if str(item).strip())


def _gte(pass_if: Mapping[str, Any] | None, *, default: float | None) -> float | None:
    if not isinstance(pass_if, Mapping) or "gte" not in pass_if:
        return default
    try:
        return float(pass_if.get("gte"))
    except (TypeError, ValueError):
        return default


def coerce_extra_answer(raw: Any, *, kind: str | None = None) -> Any:
    """Turn a schema scalar into the mapping shape Decisions answers use."""
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str) and raw.strip():
        return {"choice": raw.strip()}
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        if kind == "score":
            return {"score": float(raw)}
        return {"probability": float(raw)}
    return raw


def _extract_probability(answer: Any) -> float | None:
    if isinstance(answer, (int, float)) and not isinstance(answer, bool):
        return float(answer)
    if not isinstance(answer, Mapping):
        return None
    raw = answer.get("probability")
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return float(raw)
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
