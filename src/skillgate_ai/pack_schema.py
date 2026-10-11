"""Pack-level scoring extras and seed-case lock. Schema 1 stays additive."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from skillgate_ai.errors import SuiteError, friendly_validation_error

SEED_CASE_IDS = {
    "pdf": frozenset(
        {
            "extract-hello",
            "merge-alpha-beta",
            "create-status",
            "trigger-notes-pdf",
            "trigger-combine-decks",
            "no-trigger-unrelated",
            "extract-invoice",
            "rotate-hello",
        }
    ),
    "pdf-sabotaged": frozenset(
        {
            "extract-hello",
            "merge-alpha-beta",
            "create-status",
            "trigger-notes-pdf",
            "trigger-combine-decks",
            "no-trigger-unrelated",
            "extract-invoice",
            "rotate-hello",
        }
    ),
}


class ExtraQuestion(BaseModel):
    id: str
    type: Literal["predicate", "choice", "score"]
    ask: str
    on_fail: Literal["block", "warn"] = "block"
    choices: list[dict[str, Any]] | None = None
    levels: list[str] | None = None
    pass_if: dict[str, Any] | None = None
    include_when: str | None = None


class JudgeBlock(BaseModel):
    min_confidence: float | None = None
    on_fail: dict[str, Literal["block", "warn"]] | None = None
    extra_questions: list[ExtraQuestion] = Field(default_factory=list)
    score_no_trigger: bool = False

    def is_empty(self) -> bool:
        return (
            self.min_confidence is None
            and not self.on_fail
            and not self.extra_questions
            and not self.score_no_trigger
        )

    def to_sparse_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.min_confidence is not None:
            payload["min_confidence"] = self.min_confidence
        if self.on_fail:
            payload["on_fail"] = dict(self.on_fail)
        if self.extra_questions:
            payload["extra_questions"] = [
                item.model_dump(exclude_none=True) for item in self.extra_questions
            ]
        if self.score_no_trigger:
            payload["score_no_trigger"] = True
        return payload


def case_is_locked(skill: str, case_id: str) -> bool:
    return case_id in SEED_CASE_IDS.get(skill, frozenset())


def parse_judge_block(raw: object) -> JudgeBlock | None:
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        block = JudgeBlock.model_validate(raw)
    except Exception as exc:
        raise SuiteError(friendly_validation_error(exc, kind="Judge")) from exc
    return None if block.is_empty() else block
