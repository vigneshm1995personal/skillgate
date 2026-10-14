"""Eval suite loader — YAML next to skills/, not infra jargon."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator

from skillgate_ai.errors import SuiteError, friendly_validation_error
from skillgate_ai.metrics import CaseBudgets

# Live cursor-agent / Codex tasks routinely need >120s. Env SKILLGATE_TASK_TIMEOUT_SEC still wins.
DEFAULT_TASK_TIMEOUT_SEC = 300


class FileCopy(BaseModel):
    src: str
    dest: str


class FileExpect(BaseModel):
    path: str
    exists: bool = True
    contains: str | None = None
    min_bytes: int | None = None
    min_pages: int | None = None
    max_pages: int | None = None


class RubricCheck(BaseModel):
    id: str
    file: str | None = None
    contains: str | None = None
    min_bytes: int | None = None
    pdf_pages: int | None = None
    description: str | None = None


class ScorerSpec(BaseModel):
    type: Literal["skill_trigger", "task_completion", "rubric", "answer_contains"]
    files: list[FileExpect] = Field(default_factory=list)
    checks: list[RubricCheck] = Field(default_factory=list)
    answer: list[str] = Field(default_factory=list)
    min_score: float = 1.0


class TaskSpec(BaseModel):
    id: str
    prompt: str
    expect_skill: str | None = None
    files: list[FileCopy] = Field(default_factory=list)
    scorers: list[ScorerSpec]
    timeout_sec: int | None = None
    budgets: CaseBudgets | None = None

    @field_validator("id")
    @classmethod
    def _id_ok(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task id is required")
        return value.strip()


class SuiteSpec(BaseModel):
    suite: str
    skill: str
    skills: list[str] = Field(default_factory=list)
    title: str | None = None
    description: str | None = None
    timeout_sec: int = DEFAULT_TASK_TIMEOUT_SEC
    tasks: list[TaskSpec]

    @field_validator("tasks")
    @classmethod
    def _tasks_ok(cls, value: list[TaskSpec]) -> list[TaskSpec]:
        if not value:
            raise ValueError("suite must have at least one task")
        ids = [t.id for t in value]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate task ids: {sorted(dupes)}")
        return value

    def skill_paths(self) -> list[str]:
        if self.skills:
            return list(self.skills)
        return [self.skill]


def load_suite(path: str | Path) -> tuple[SuiteSpec, Path]:
    suite_path = Path(path).expanduser().resolve()
    if not suite_path.is_file():
        raise SuiteError(f"Eval suite not found: {suite_path}")
    try:
        raw = yaml.safe_load(suite_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        raise SuiteError("Eval suite is not valid YAML.") from None
    if not isinstance(raw, dict):
        raise SuiteError("Eval suite must be a YAML mapping")
    if "cases" in raw and "tasks" not in raw:
        raise SuiteError(
            "That YAML is a checks file, not a suite. Pass the skill folder instead, "
            "for example: skillgate check <folder>.",
        )
    from_pack = str(raw.get("from_pack") or "").strip()
    if from_pack:
        skill_dir = _resolve_from_pack(suite_path, from_pack)
        from skillgate_ai.case_pack import expand_from_pack

        spec = expand_from_pack(skill_dir)
        return spec, suite_path.parent
    raw = _normalize_suite(raw)
    try:
        spec = SuiteSpec.model_validate(raw)
    except Exception as exc:
        raise SuiteError(friendly_validation_error(exc, kind="Eval suite", raw=raw)) from None
    return spec, suite_path.parent


def _resolve_from_pack(suite_path: Path, rel: str) -> Path:
    rel_path = Path(rel)
    if rel_path.is_absolute():
        return rel_path
    if suite_path.parent.name == "evals":
        return (suite_path.parent.parent / rel).resolve()
    return (suite_path.parent / rel).resolve()


def discover_suites(evals_root: str | Path) -> list[Path]:
    root = Path(evals_root)
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if p.suffix in {".yaml", ".yml"} and p.is_file())


def _normalize_suite(raw: dict[str, Any]) -> dict[str, Any]:
    """Allow a slightly friendlier YAML where scorers can be a type string."""
    tasks = raw.get("tasks") or []
    normalized = []
    for task in tasks:
        if not isinstance(task, dict):
            normalized.append(task)
            continue
        scorers = []
        for scorer in task.get("scorers") or []:
            if isinstance(scorer, str):
                scorers.append({"type": scorer})
            elif isinstance(scorer, dict) and "type" in scorer:
                scorers.append(scorer)
            elif isinstance(scorer, dict) and len(scorer) == 1:
                type_name, body = next(iter(scorer.items()))
                entry = {"type": type_name}
                if isinstance(body, dict):
                    entry.update(body)
                scorers.append(entry)
            else:
                scorers.append(scorer)
        task = {**task, "scorers": scorers}
        normalized.append(task)
    return {**raw, "tasks": normalized}
