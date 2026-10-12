"""Pack-level scoring extras and seed-case lock. Schema 1 stays additive."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

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

CASES_RELS = frozenset({"evals/cases.yaml", "evals/cases.yml"})
SEED_LOCK_MESSAGE = "This pack's original checks stay. Add a new check instead of deleting them."
SEED_LOCK_HINT = "Add a new check instead of deleting the original ones."
SEED_EDIT_MESSAGE = "This pack's original checks stay. Add a new check instead of editing them."
SEED_EDIT_HINT = "Add a new check instead of editing the original ones."


class ExtraQuestion(BaseModel):
    id: str
    type: Literal["predicate", "choice", "score"]
    ask: str
    on_fail: Literal["block", "warn"] = "block"
    choices: list[dict[str, Any]] | None = None
    levels: list[str] | None = None
    pass_if: dict[str, Any] | None = None
    include_when: str | None = None

    @field_validator("on_fail", mode="before")
    @classmethod
    def _on_fail_plain(cls, value: object) -> str:
        from skillgate_ai.judge_spec import _on_fail_value

        try:
            return _on_fail_value(value, default="block")
        except SuiteError as exc:
            raise ValueError(exc.message) from exc


class JudgeBlock(BaseModel):
    min_confidence: float | None = None
    on_fail: dict[str, Literal["block", "warn"]] | None = None
    extra_questions: list[ExtraQuestion] = Field(default_factory=list)
    score_no_trigger: bool = False

    @model_validator(mode="after")
    def _unique_extra_ids(self) -> JudgeBlock:
        seen: set[str] = set()
        for question in self.extra_questions:
            if question.id in seen:
                raise ValueError(f"`{question.id}` is already a scoring question. Pick a new id.")
            seen.add(question.id)
        return self

    @field_validator("on_fail", mode="before")
    @classmethod
    def _on_fail_map(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        from skillgate_ai.judge_spec import _on_fail_value

        try:
            return {str(key): _on_fail_value(item, default="block") for key, item in value.items()}
        except SuiteError as exc:
            raise ValueError(exc.message) from exc

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


def case_id_slug(value: object) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or "case"


def case_is_locked(skill: str, case_id: str) -> bool:
    return case_id_slug(case_id) in SEED_CASE_IDS.get(skill, frozenset())


def refuse_locked_prompt_change(skill: str, case_id: str, old_prompt: str, new_prompt: str) -> None:
    if case_is_locked(skill, case_id) and old_prompt != new_prompt:
        raise SuiteError(SEED_EDIT_MESSAGE, hint=SEED_EDIT_HINT)


def keep_locked_case(skill: str, by_id: Mapping[str, Any], raw: Mapping[str, Any]) -> Any:
    case_id = case_id_slug(raw.get("id") or "")
    existing = by_id.get(case_id)
    if existing is None or not case_is_locked(skill, case_id):
        return None
    if "prompt" in raw:
        refuse_locked_prompt_change(skill, case_id, existing.prompt, str(raw.get("prompt") or ""))
    return existing


def reject_missing_seed_cases(skill: str, case_ids: Iterable[str]) -> None:
    locked = SEED_CASE_IDS.get(skill)
    if not locked:
        return
    present = {item for item in case_ids if item}
    missing = sorted(locked - present)
    if missing:
        raise SuiteError(SEED_LOCK_MESSAGE, hint=SEED_LOCK_HINT, exit_code=2)


def guard_cases_yaml_write(root: Path, rel: str, content: str | bytes) -> None:
    cleaned = rel.replace("\\", "/").lstrip("/")
    if cleaned not in CASES_RELS:
        return
    try:
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        raw = yaml.safe_load(text) or {}
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise SuiteError(
            "Couldn't load these checks.",
            hint="evals/cases.yaml must be valid YAML.",
        ) from exc
    if not isinstance(raw, dict):
        raise SuiteError(
            "Couldn't load these checks.",
            hint="evals/cases.yaml must be a YAML mapping.",
        )
    cases = raw.get("cases") or []
    ids: set[str] = set()
    if isinstance(cases, list):
        for item in cases:
            if isinstance(item, dict) and item.get("id"):
                ids.add(str(item.get("id")))
    skill = str(raw.get("skill") or root.name).strip()
    reject_missing_seed_cases(skill, ids)
    reject_missing_seed_cases(root.name, ids)


def merge_judge_block(
    existing: JudgeBlock | None,
    incoming: JudgeBlock | None,
    *,
    removed_ids: Iterable[str] | None = None,
) -> JudgeBlock | None:
    removed = {str(item).strip() for item in (removed_ids or []) if str(item).strip()}
    by_id: dict[str, ExtraQuestion] = {}
    if existing is not None:
        for question in existing.extra_questions:
            if question.id not in removed:
                by_id[question.id] = question
    if incoming is not None:
        for question in incoming.extra_questions:
            by_id[question.id] = question
    extras = list(by_id.values())
    if incoming is None:
        if existing is None:
            return None
        block = existing.model_copy(update={"extra_questions": extras})
        return None if block.is_empty() else block
    updates: dict[str, Any] = {"extra_questions": extras}
    if incoming.on_fail is None and existing is not None and existing.on_fail:
        updates["on_fail"] = existing.on_fail
    if incoming.min_confidence is None and existing is not None:
        updates["min_confidence"] = existing.min_confidence
    block = incoming.model_copy(update=updates)
    return None if block.is_empty() else block


def parse_judge_patch(raw: object) -> tuple[JudgeBlock | None, list[str]]:
    if not isinstance(raw, dict):
        return parse_judge_block(raw), []
    payload = dict(raw)
    removed_raw = payload.pop("removed_extra_ids", None) or []
    if not isinstance(removed_raw, list):
        removed_raw = [removed_raw]
    removed = [str(item).strip() for item in removed_raw if str(item).strip()]
    return parse_judge_block(payload), removed


def parse_judge_block(raw: object) -> JudgeBlock | None:
    if not isinstance(raw, dict) or not raw:
        return None
    try:
        block = JudgeBlock.model_validate(raw)
    except Exception as exc:
        raise SuiteError(friendly_validation_error(exc, kind="Judge")) from exc
    return None if block.is_empty() else block
