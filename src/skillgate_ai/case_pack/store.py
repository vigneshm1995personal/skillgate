"""Author I/O pack: cases.yaml + fixtures inputs + golden outputs.

The skill directory is the only blob store. Pinned cases are the Deploy trust
path; drafts and suggest-from-skill checks are not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from skillgate_ai.case_pack.models import (
    CASES_REL,
    NO_TRIGGER_OUTPUT_WARNING,
    CasePack,
    _reject_missing_seed_cases,
    _reject_removed_seed_cases,
)
from skillgate_ai.errors import SuiteError, friendly_validation_error
from skillgate_ai.ingest import folder_matches_skill
from skillgate_ai.pack_files import (
    GOLDEN_TAIL_CHARS as GOLDEN_TAIL_CHARS,
)
from skillgate_ai.pack_schema import (
    ExtraQuestion as ExtraQuestion,
)
from skillgate_ai.pack_schema import (
    merge_judge_block,
    parse_judge_patch,
)


def pack_judge_dict(pack: CasePack | None) -> dict[str, Any] | None:
    if pack is None or pack.judge is None or pack.judge.is_empty():
        return None
    return pack.judge.to_sparse_dict()


def save_pack_judge(skill_path: str | Path, raw: dict[str, Any] | None) -> CasePack:
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise SuiteError("This skill has no case pack yet.")
    incoming, removed = parse_judge_patch(raw)
    merged = merge_judge_block(pack.judge, incoming, removed_ids=removed)
    updated = pack.model_copy(update={"judge": merged})
    save_case_pack(root, updated)
    return updated


def reset_pack_judge(skill_path: str | Path) -> CasePack:
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise SuiteError("This skill has no case pack yet.")
    cases = [case.model_copy(update={"judge": None}) for case in pack.cases]
    updated = pack.model_copy(update={"judge": None, "cases": cases})
    save_case_pack(root, updated)
    return updated


def expected_without_target_warning(
    *,
    contains: str | None,
    output_path: str | None,
    golden_path: str | None,
    should_trigger: bool = True,
) -> str | None:
    if not should_trigger:
        leftover = bool(
            str(contains or "").strip()
            or str(output_path or "").strip()
            or str(golden_path or "").strip()
        )
        return NO_TRIGGER_OUTPUT_WARNING if leftover else None
    return None


def cases_path(skill_path: str | Path) -> Path:
    return Path(skill_path).expanduser().resolve() / CASES_REL


def load_case_pack(skill_path: str | Path) -> CasePack | None:
    """Load evals/cases.yaml, or None when the file is absent."""
    root = Path(skill_path).expanduser().resolve()
    path = cases_path(root)
    if not path.is_file():
        return None
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        raise SuiteError(
            "Couldn't load these checks.",
            hint="evals/cases.yaml must be valid YAML.",
        ) from None
    if not isinstance(raw, dict):
        raise SuiteError(
            "Couldn't load these checks.",
            hint="evals/cases.yaml must be a YAML mapping.",
        )
    schema = raw.get("schema")
    if schema is not None and schema != 1:
        raise SuiteError(
            f"This case pack uses schema {schema}; Skill Gate supports schema 1.",
            hint="Set `schema: 1` in evals/cases.yaml.",
            exit_code=2,
        )
    try:
        pack = CasePack.model_validate(raw)
    except ValidationError as exc:
        raise SuiteError(
            friendly_validation_error(exc, kind="Case pack", raw=raw),
            exit_code=2,
        ) from None
    folder = root.name
    if not folder_matches_skill(folder, pack.skill):
        raise SuiteError(
            f"This check file is for `{pack.skill}`, but the folder is `{folder}`.",
            hint="Set `skill:` in evals/cases.yaml to the folder name.",
        )
    _validate_pack_on_disk(root, pack)
    _reject_missing_seed_cases(pack, root)
    return pack


def save_case_pack(skill_path: str | Path, pack: CasePack) -> Path:
    root = Path(skill_path).expanduser().resolve()
    try:
        CasePack.model_validate(pack.model_dump())
    except ValidationError as exc:
        raise SuiteError(friendly_validation_error(exc, kind="Case pack")) from None
    dest = cases_path(root)
    previous = None
    if dest.is_file():
        try:
            raw = yaml.safe_load(dest.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                previous = CasePack.model_validate(raw)
        except (OSError, UnicodeDecodeError, yaml.YAMLError, ValidationError):
            previous = None
    _reject_removed_seed_cases(previous, pack)
    _reject_missing_seed_cases(pack, root)
    _validate_pack_on_disk(root, pack)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_dump_pack(pack), encoding="utf-8")
    return dest


def _dump_pack(pack: CasePack) -> str:
    payload = pack.model_dump(mode="python", by_alias=True)
    if pack.budgets is None or pack.budgets.is_empty():
        payload.pop("budgets", None)
    else:
        payload["budgets"] = pack.budgets.to_sparse_dict()
    if pack.judge is None or pack.judge.is_empty():
        payload.pop("judge", None)
    else:
        payload["judge"] = pack.judge.to_sparse_dict()
    dumped_cases = payload.get("cases") or []
    for item, case in zip(dumped_cases, pack.cases):  # noqa: B905
        if not isinstance(item, dict):
            continue
        if case.budgets is None or case.budgets.is_empty():
            item.pop("budgets", None)
        else:
            item["budgets"] = case.budgets.to_sparse_dict()
        if case.judge is None or case.judge.is_empty():
            item.pop("judge", None)
        else:
            item["judge"] = case.judge.to_sparse_dict()
        if not case.trigger_mode:
            item.pop("trigger_mode", None)
        if not case.output_optional:
            item.pop("output_optional", None)
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def _validate_pack_on_disk(root: Path, pack: CasePack) -> None:
    for case in pack.cases:
        if case.input.needs_upload:
            continue
        for item in case.input.files:
            src = root / item.src
            if not src.is_file():
                raise SuiteError(
                    f"Couldn't find {item.src} (listed as an input file for {case.id}).",
                    hint="Add the file under evals/fixtures/, or remove it from input.files.",
                )
        if (
            case.status == "pinned"
            and case.should_trigger
            and case.golden is not None
            and not case.output_optional
            and not (root / case.golden.path).is_file()
        ):
            from skillgate_ai.case_pack.dataset import MISSING_GOLDEN_REASON

            raise SuiteError(f"{case.id}: {MISSING_GOLDEN_REASON}")
