"""Resolve built-in + extra judge questions. No HTTP."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from skillgate_ai.errors import SuiteError
from skillgate_ai.judge_bank import (
    CHECK_CELL_LABELS,
    CHECK_CELL_ORDER,
    DEFAULT_MIN_CONFIDENCE,
    SOFT_CELL_LABELS,
    SOFT_CELL_ORDER,
    with_evidence_rule,
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
    covered_by: tuple[str, ...] | None = None

    @property
    def label(self) -> str:
        if self.builtin and self.id in CHECK_CELL_LABELS:
            return CHECK_CELL_LABELS[self.id]
        if self.builtin and self.id in SOFT_CELL_LABELS:
            return SOFT_CELL_LABELS[self.id]
        return self.ask

    def to_decisions(self) -> dict[str, Any]:
        instructions = with_evidence_rule(self.ask)
        if self.type == "predicate":
            return {"type": "predicate", "name": self.id, "instructions": instructions}
        if self.type == "score":
            labels = list(self.levels) or ["1", "2", "3", "4", "5"]
            return {
                "type": "score",
                "name": self.id,
                "instructions": instructions,
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
            "instructions": instructions,
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


def _on_fail_value(value: Any, *, default: str) -> str:
    if value is None or str(value).strip() == "":
        return default
    raw = str(value).strip().lower()
    if raw in {"block", "fail", "fail the check"}:
        return "block"
    if raw in {"warn", "warn only", "warning"}:
        return "warn"
    raise SuiteError("on_fail must be Fail the check or Warn only.", exit_code=2)
