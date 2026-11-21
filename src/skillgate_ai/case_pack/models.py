"""Author I/O pack: cases.yaml + fixtures inputs + golden outputs.

The skill directory is the only blob store. Pinned cases are the Deploy trust
path; drafts and suggest-from-skill checks are not.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from skillgate_ai.errors import SuiteError
from skillgate_ai.metrics import CaseBudgets
from skillgate_ai.pack import (
    GOLDEN_DIR,
)
from skillgate_ai.pack_files import (
    GOLDEN_TAIL_CHARS as GOLDEN_TAIL_CHARS,
)
from skillgate_ai.pack_schema import (
    SEED_CASE_IDS,
    SEED_LOCK_HINT,
    SEED_LOCK_MESSAGE,
    JudgeBlock,
    reject_missing_seed_cases,
)
from skillgate_ai.pack_schema import (
    ExtraQuestion as ExtraQuestion,
)
from skillgate_ai.suite import SuiteSpec

CASES_REL = "evals/cases.yaml"

PIN_NEEDS_EXPECTED = "Add expected output for this check, then save."

PIN_NEEDS_EXPECTED_HINT = "Open Dataset and fill Expected output."

NO_TRIGGER_OUTPUT_WARNING = "Expected output on a no-trigger check is ignored."

EXPECTED_WITHOUT_TARGET = "This check has expected text, but no output file to compare it with."

PACK_FINGERPRINT_FIELDS = ("id", "prompt", "should_trigger", "input", "golden", "budgets", "judge")

_CASE_ID_RE = re.compile(r"^[a-z0-9-]+$")

_JSONISH_RE = re.compile(r"^\s*[\{\[]")


class CaseFileCopy(BaseModel):
    src: str
    dest: str


class CaseInput(BaseModel):
    files: list[CaseFileCopy] = Field(default_factory=list)
    needs_upload: bool = False


class CaseGolden(BaseModel):
    output_path: str
    path: str
    kind: Literal["json", "text", "bytes"] = "text"

    @field_validator("path")
    @classmethod
    def _golden_dir(cls, value: str) -> str:
        cleaned = value.replace("\\", "/").lstrip("/")
        if not cleaned.startswith(f"{GOLDEN_DIR}/"):
            raise ValueError(f"golden.path must live under {GOLDEN_DIR}/")
        if ".." in Path(cleaned).parts:
            raise ValueError("golden.path must stay inside the skill folder")
        return cleaned


class PackCase(BaseModel):
    id: str
    status: Literal["pinned", "draft"] = "draft"
    prompt: str
    should_trigger: bool = True
    input: CaseInput = Field(default_factory=CaseInput)
    golden: CaseGolden | None = None
    contains: list[str] = Field(default_factory=list)
    min_pages: int | None = None
    budgets: CaseBudgets | None = None
    judge: JudgeBlock | None = None
    trigger_mode: bool = False
    output_optional: bool = False

    @field_validator("output_optional", mode="before")
    @classmethod
    def _output_optional_flag(cls, value: object) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return bool(value)

    @field_validator("id")
    @classmethod
    def _id_ok(cls, value: str) -> str:
        slug = (value or "").strip()
        if not _CASE_ID_RE.match(slug):
            raise ValueError("case id must be lowercase letters, digits, and hyphens")
        return slug

    @field_validator("contains", mode="before")
    @classmethod
    def _contains_list(cls, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return []


class CasePack(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    schema_version: Literal[1] = Field(alias="schema")
    skill: str
    cases: list[PackCase]
    budgets: CaseBudgets | None = None
    judge: JudgeBlock | None = None

    @model_validator(mode="after")
    def _unique_ids(self) -> CasePack:
        ids = [case.id for case in self.cases]
        dupes = sorted({item for item in ids if ids.count(item) > 1})
        if dupes:
            names = ", ".join(dupes)
            raise ValueError(f"These checks use the same id: {names}")
        return self


@dataclass(frozen=True)
class TrustSuite:
    fingerprint: str
    case_ids: tuple[str, ...]
    source: Literal["pack", "bundled_suite", "template"]
    suite: SuiteSpec


def _reject_missing_seed_cases(pack: CasePack, pack_root: Path) -> None:
    ids = {case.id for case in pack.cases}
    reject_missing_seed_cases(pack.skill, ids, pack_root=pack_root)
    reject_missing_seed_cases(pack_root.name, ids, pack_root=pack_root)


def _reject_removed_seed_cases(previous: CasePack | None, pack: CasePack) -> None:
    locked = SEED_CASE_IDS.get(pack.skill)
    if not locked or previous is None:
        return
    prev_ids = {case.id for case in previous.cases}
    present = {case.id for case in pack.cases}
    missing = sorted((locked & prev_ids) - present)
    if missing:
        raise SuiteError(SEED_LOCK_MESSAGE, hint=SEED_LOCK_HINT, exit_code=2)
