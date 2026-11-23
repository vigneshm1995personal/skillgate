"""Resolve built-in + extra judge questions. No HTTP."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from skillgate_ai.errors import SuiteError
from skillgate_ai.judge_bank import DEFAULT_MIN_CONFIDENCE
from skillgate_ai.judge_spec.model import (
    CAP_MESSAGE,
    MAX_QUESTIONS,
    QUESTION_ID_RE,
    RESERVED_ID_MESSAGE,
    RESERVED_IDS,
    TYPE_ALIASES,
    TYPE_MESSAGE,
    JudgeQuestion,
    JudgeSpec,
    _on_fail_value,
    builtin_questions,
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
                min_confidence = float(layer["min_confidence"])
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
        suggested = re.sub(r"[^a-z0-9]+", "_", qid.lower()).strip("_")[:64]
        hint = "The question was not added. Fix the id before running a check."
        if suggested and suggested != qid and QUESTION_ID_RE.match(suggested):
            hint = f"Use underscores: {suggested}. {hint}"
        elif "-" in qid:
            hint = f"Use underscores, not hyphens. {hint}"
        raise SuiteError(
            "Extra question id must be lowercase letters, digits, and underscores (max 64).",
            hint=hint,
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
    raw_covered = raw.get("covered_by")
    covered_by: tuple[str, ...] | None = None
    if raw_covered is not None:
        if isinstance(raw_covered, list):
            covered_by = tuple(str(item).strip() for item in raw_covered if str(item).strip())
        else:
            covered_by = ()
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
        covered_by=covered_by,
    )


def _extra_list(raw: Any) -> list[Mapping[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SuiteError("extra_questions must be a list.", exit_code=2)
    return [item for item in raw if item is not None]


def _parse_choices(raw: Any, *, qid: str, kind: str) -> tuple[dict[str, Any], ...]:
    if kind != "choice":
        return ()
    if not isinstance(raw, list) or len(raw) < 2:
        raise SuiteError(
            f"Question {qid}: pick-one questions need at least two choices.", exit_code=2
        )
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
