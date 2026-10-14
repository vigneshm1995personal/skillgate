"""Author I/O pack: cases.yaml + fixtures inputs + golden outputs.

The skill directory is the only blob store. Pinned cases are the Deploy trust
path; drafts and suggest-from-skill checks are not.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from skillgate_ai.errors import SuiteError, friendly_validation_error
from skillgate_ai.ingest import folder_matches_skill
from skillgate_ai.metrics import CaseBudgets, merge_budgets, parse_budgets
from skillgate_ai.pack import (
    FIXTURE_DIR,
    GOLDEN_DIR,
    copy_into_pack,
    pack_preview,
    safe_relpath,
    write_pack_file,
)
from skillgate_ai.pack_files import (
    GOLDEN_TAIL_CHARS as GOLDEN_TAIL_CHARS,
    golden_kind,
    read_capped_text,
    resolve_golden_src,
    sniff_output_bytes,
)
from skillgate_ai.pack_schema import (
    ExtraQuestion as ExtraQuestion,
    JudgeBlock,
    SEED_CASE_IDS,
    SEED_LOCK_HINT,
    SEED_LOCK_MESSAGE,
    case_id_slug,
    case_is_locked,
    keep_locked_case,
    merge_judge_block,
    parse_judge_block,
    parse_judge_patch,
    reject_missing_seed_cases,
)
from skillgate_ai.suite import DEFAULT_TASK_TIMEOUT_SEC, SuiteSpec, _normalize_suite

CASES_REL = "evals/cases.yaml"
PIN_NEEDS_EXPECTED = "Add expected output for this check, then save."
PIN_NEEDS_EXPECTED_HINT = "Open Dataset and fill Expected output."
NO_TRIGGER_OUTPUT_WARNING = "Expected output on a no-trigger check is ignored."
EXPECTED_WITHOUT_TARGET = (
    "This check has expected text, but no output file to compare it with."
)
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
    schema_version: Literal[1] = Field(default=1, alias="schema")
    skill: str
    cases: list[PackCase]
    budgets: CaseBudgets | None = None
    judge: JudgeBlock | None = None

    @model_validator(mode="after")
    def _unique_ids(self) -> CasePack:
        ids = [case.id for case in self.cases]
        dupes = sorted({item for item in ids if ids.count(item) > 1})
        if dupes:
            raise ValueError(f"duplicate case ids: {dupes}")
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
    if not str(contains or "").strip():
        return None
    if str(output_path or "").strip() or str(golden_path or "").strip():
        return None
    return EXPECTED_WITHOUT_TARGET


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
    except Exception as exc:
        raise SuiteError(friendly_validation_error(exc, kind="Case pack", raw=raw)) from None
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
    except Exception as exc:
        raise SuiteError(friendly_validation_error(exc, kind="Case pack")) from None
    dest = cases_path(root)
    previous = None
    if dest.is_file():
        try:
            raw = yaml.safe_load(dest.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                previous = CasePack.model_validate(raw)
        except Exception:
            previous = None
    _reject_removed_seed_cases(previous, pack)
    _reject_missing_seed_cases(pack, root)
    _validate_pack_on_disk(root, pack)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(_dump_pack(pack), encoding="utf-8")
    return dest


def pack_fingerprint(pack: CasePack) -> str:
    pinned = []
    for case in pack.cases:
        if case.status != "pinned":
            continue
        dump = case.model_dump(include=set(PACK_FINGERPRINT_FIELDS) - {"budgets", "judge"})
        effective = merge_budgets(pack.budgets, case.budgets)
        if effective is not None:
            dump["budgets"] = effective.to_sparse_dict()
        if case.judge is not None and not case.judge.is_empty():
            dump["judge"] = case.judge.to_sparse_dict()
        pinned.append(dump)
    payload: dict[str, Any] = {"cases": pinned}
    if pack.judge is not None and not pack.judge.is_empty():
        payload["pack_judge"] = pack.judge.to_sparse_dict()
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def suite_fingerprint(spec: SuiteSpec) -> str:
    payload = []
    for task in spec.tasks:
        row: dict[str, Any] = {
            "id": task.id,
            "prompt": task.prompt,
            "expect_skill": task.expect_skill,
            "files": [{"src": item.src, "dest": item.dest} for item in task.files],
            "contains": [
                item.contains for scorer in task.scorers for item in scorer.files if item.contains
            ],
        }
        effective = parse_budgets(task.budgets)
        if effective is not None:
            row["budgets"] = effective.to_sparse_dict()
        payload.append(row)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def suite_from_pack(pack: CasePack, skill_rel: str) -> SuiteSpec:
    pinned = [case for case in pack.cases if case.status == "pinned"]
    if not pinned:
        raise SuiteError("This Dataset has no saved checks to run.")
    raw_tasks: list[dict[str, Any]] = []
    for case in pinned:
        scorers: list[dict[str, Any]] = [{"type": "skill_trigger"}]
        if case.golden and case.should_trigger:
            expects: list[dict[str, Any]] = []
            if case.contains:
                for item in case.contains:
                    entry: dict[str, Any] = {
                        "path": case.golden.output_path,
                        "contains": item,
                    }
                    if case.min_pages is not None and not expects:
                        entry["min_pages"] = case.min_pages
                    expects.append(entry)
            else:
                entry = {"path": case.golden.output_path}
                if case.min_pages is not None:
                    entry["min_pages"] = case.min_pages
                expects.append(entry)
            scorers.append({"type": "task_completion", "files": expects})
            rubric: dict[str, Any] = {
                "id": "output-exists",
                "file": case.golden.output_path,
                "min_bytes": 1,
            }
            if case.contains:
                rubric["contains"] = case.contains[0]
            scorers.append({"type": "rubric", "min_score": 1.0, "checks": [rubric]})
        task_raw: dict[str, Any] = {
            "id": case.id,
            "prompt": case.prompt,
            "expect_skill": pack.skill if case.should_trigger else None,
            "files": [{"src": item.src, "dest": item.dest} for item in case.input.files],
            "scorers": scorers,
        }
        effective = merge_budgets(pack.budgets, case.budgets)
        if effective is not None:
            task_raw["budgets"] = effective.to_sparse_dict()
        raw_tasks.append(task_raw)
    raw = _normalize_suite(
        {
            "suite": f"{pack.skill}-pack",
            "skill": skill_rel,
            "title": "Dataset",
            "description": "This skill's Dataset.",
            "timeout_sec": DEFAULT_TASK_TIMEOUT_SEC,
            "tasks": raw_tasks,
        }
    )
    try:
        return SuiteSpec.model_validate(raw)
    except Exception as exc:
        raise SuiteError(f"Couldn't turn these checks into a run: {exc}") from exc


def checks_from_pack(pack: CasePack, *, include_drafts: bool = False) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for case in pack.cases:
        if case.status != "pinned" and not include_drafts:
            continue
        contains = case.contains[0] if case.contains else None
        check: dict[str, Any] = {
            "id": case.id,
            "prompt": case.prompt,
            "should_trigger": case.should_trigger,
            "files": [{"src": item.src, "dest": item.dest} for item in case.input.files],
            "needs_upload": case.input.needs_upload,
            "output_path": case.golden.output_path if case.golden else None,
            "contains": contains,
            "min_pages": case.min_pages,
            "golden_path": case.golden.path if case.golden else None,
            "golden_kind": case.golden.kind if case.golden else None,
            "bank_status": case.status,
            "locked": case_is_locked(
                pack.skill, case.id, pack_case_ids=[c.id for c in pack.cases]
            ),
        }
        if case.judge is not None and not case.judge.is_empty():
            check["judge"] = case.judge.to_sparse_dict()
        warning = no_trigger_output_warning(case)
        if warning is None and case.contains and case.golden is None:
            warning = EXPECTED_WITHOUT_TARGET
        if warning:
            check["warning"] = warning
        effective = merge_budgets(pack.budgets, case.budgets)
        if effective is not None:
            check["budgets"] = effective.to_sparse_dict()
        checks.append(check)
    return checks


def skill_has_dataset(skill_path: str | Path) -> bool:
    try:
        pack = load_case_pack(skill_path)
    except SuiteError:
        return False
    return bool(pack and any(case.status == "pinned" for case in pack.cases))


def dataset_view(skill_path: str | Path) -> dict[str, Any] | None:
    """Dataset listing: examples with input and expected-output previews."""
    root = Path(skill_path).expanduser().resolve()
    if not root.is_dir():
        return None
    pack = load_case_pack(root)
    if pack is None:
        return {
            "skill": _skill_name(root),
            "fingerprint": None,
            "cases": [],
        }
    cases: list[dict[str, Any]] = []
    for case in pack.cases:
        fixtures: list[dict[str, Any]] = []
        for item in case.input.files:
            entry = _preview_file(root, item.src)
            entry["src"] = item.src
            entry["dest"] = item.dest
            fixtures.append(entry)
        golden_payload: dict[str, Any] | None = None
        if case.golden:
            golden_payload = _preview_file(root, case.golden.path)
            golden_payload["output_path"] = case.golden.output_path
            golden_payload["kind"] = case.golden.kind
            state = golden_state(case.golden, root)
            if state and state.get("body") is not None:
                golden_payload["body"] = state["body"]
                golden_payload.setdefault("text", state["body"])
        cases.append(
            {
                "id": case.id,
                "status": case.status,
                "prompt": case.prompt,
                "should_trigger": case.should_trigger,
                "fixtures": fixtures,
                "golden": golden_payload,
            }
        )
    return {
        "skill": pack.skill,
        "fingerprint": pack_fingerprint(pack),
        "cases": cases,
    }


def _preview_file(root: Path, rel: str) -> dict[str, Any]:
    try:
        return pack_preview(root, rel)
    except FileNotFoundError:
        return {
            "path": rel.replace("\\", "/").lstrip("/"),
            "kind": "missing",
            "missing": True,
        }


def pin_checks(skill_path: str | Path, checks: list[dict[str, Any]]) -> CasePack:
    """Upsert checks into evals/cases.yaml as pinned cases."""
    root = Path(skill_path).expanduser().resolve()
    skill_name = _skill_name(root)
    existing = None
    path = cases_path(root)
    if path.is_file():
        existing = load_case_pack(root)
    by_id: dict[str, PackCase] = {case.id: case for case in (existing.cases if existing else [])}
    if not checks:
        raise ValueError("Pin needs at least one check.")
    pack_ids = list(by_id.keys()) + [
        case_id_slug(raw.get("id") or "") for raw in checks if raw.get("id")
    ]
    for raw in checks:
        if keep_locked_case(skill_name, by_id, raw, pack_case_ids=pack_ids) is not None:
            continue
        case = _case_from_check(root, raw, skill_name)
        by_id[case.id] = case
    pack = CasePack(
        schema_version=1,
        skill=skill_name,
        cases=list(by_id.values()),
        budgets=existing.budgets if existing else None,
        judge=existing.judge if existing else None,
    )
    _reject_missing_seed_cases(pack, root)
    save_case_pack(root, pack)
    return pack


def pin_case_ids(skill_path: str | Path, case_ids: list[str]) -> CasePack:
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise ValueError("This skill has no case pack to pin into.")
    wanted = {item.strip() for item in case_ids if str(item).strip()}
    if not wanted:
        raise ValueError("Pin needs at least one case id.")
    updated: list[PackCase] = []
    found: set[str] = set()
    for case in pack.cases:
        if case.id in wanted:
            found.add(case.id)
            if case.should_trigger and case.golden is None:
                attached = _disk_golden(root, case.id, None)
                if attached is None:
                    raise ValueError(PIN_NEEDS_EXPECTED)
                updated.append(
                    case.model_copy(update={"status": "pinned", "golden": attached})
                )
                continue
            updated.append(case.model_copy(update={"status": "pinned"}))
        else:
            updated.append(case)
    missing = sorted(wanted - found)
    if missing:
        raise ValueError(f"Unknown case ids: {', '.join(missing)}")
    out = CasePack(
        schema_version=1,
        skill=pack.skill,
        cases=updated,
        budgets=pack.budgets,
        judge=pack.judge,
    )
    save_case_pack(root, out)
    return out


def trust_suite_for_skill(skill_path: str | Path) -> TrustSuite | None:
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is not None:
        pinned = [case for case in pack.cases if case.status == "pinned"]
        if pinned:
            return TrustSuite(
                fingerprint=pack_fingerprint(pack),
                case_ids=tuple(case.id for case in pinned),
                source="pack",
                suite=suite_from_pack(pack, str(root)),
            )
    bundled = _bundled_suite_trust(root)
    if bundled is not None:
        return bundled
    return _template_trust(root)


def suite_from_checks(
    skill_path: str | Path,
    checks: list[dict[str, Any]],
    *,
    tryout: bool = False,
    only_listed: bool = False,
) -> SuiteSpec:
    """Build a suite from the Checks tab without writing evals/cases.yaml."""
    root = Path(skill_path).expanduser().resolve()
    skill_name = _skill_name(root)
    if not checks:
        raise SuiteError("Need at least one check to run.")
    existing = load_case_pack(root) if cases_path(root).is_file() else None
    held = {case.id: case for case in (existing.cases if existing else [])}
    try:
        cases = []
        pack_ids = [case_id_slug(row.get("id") or "") for row in checks if row.get("id")]
        pack_ids.extend(held.keys())
        for raw in checks:
            row = dict(raw)
            seed = keep_locked_case(skill_name, held, row, pack_case_ids=pack_ids)
            cases.append(seed if seed is not None else _case_from_check(root, row, skill_name))
    except ValueError as exc:
        hint = PIN_NEEDS_EXPECTED_HINT if PIN_NEEDS_EXPECTED in str(exc) else None
        raise SuiteError(str(exc), hint=hint) from exc
    if not tryout and not only_listed and existing is not None:
        present = {case.id for case in cases}
        all_ids = present | {c.id for c in existing.cases}
        cases.extend(
            c
            for c in existing.cases
            if case_is_locked(existing.skill, c.id, pack_case_ids=all_ids)
            and c.id not in present
        )
    pack = CasePack(
        schema_version=1,
        skill=skill_name,
        cases=cases,
        judge=existing.judge if existing else None,
    )
    return suite_from_pack(pack, str(root))


def expand_from_pack(skill_path: str | Path) -> SuiteSpec:
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise SuiteError(
            "This skill has no checks yet.",
            hint="Add a check first.",
        )
    return suite_from_pack(pack, str(root))


def checks_fingerprint(checks: list[dict[str, Any]], *, skill: str) -> str:
    """Fingerprint an ad-hoc Checks tab the same way as a pinned pack."""
    cases: list[PackCase] = []
    for raw in checks:
        case_id = case_id_slug(str(raw.get("id") or f"check-{len(cases) + 1}"))
        files = _file_copies(raw.get("files"))
        golden = None
        golden_path = str(raw.get("golden_path") or "").strip() or None
        output_path = str(raw.get("output_path") or "").strip() or None
        if golden_path and output_path:
            kind: Literal["json", "text", "bytes"] = (
                "json" if golden_path.endswith(".json") else "text"
            )
            golden = CaseGolden(output_path=output_path, path=golden_path, kind=kind)
        contains = raw.get("contains")
        contains_list = [contains] if isinstance(contains, str) and contains.strip() else []
        if isinstance(contains, list):
            contains_list = [str(item).strip() for item in contains if str(item).strip()]
        cases.append(
            PackCase(
                id=case_id,
                status="pinned",
                prompt=str(raw.get("prompt") or ""),
                should_trigger=bool(raw.get("should_trigger", True)),
                input=CaseInput(
                    files=files,
                    needs_upload=bool(raw.get("needs_upload")),
                ),
                golden=golden,
                contains=contains_list,
                min_pages=raw.get("min_pages"),
                budgets=parse_budgets(raw.get("budgets")),
            )
        )
    return pack_fingerprint(CasePack(schema_version=1, skill=skill, cases=cases))


def golden_state(golden: CaseGolden | None, skill_root: Path) -> dict[str, Any] | None:
    if golden is None:
        return None
    path = skill_root / golden.path
    if golden.kind == "bytes":
        return {
            "path": golden.path,
            "output_path": golden.output_path,
            "kind": golden.kind,
            "body": None,
            "note": "binary golden; compare path presence only",
        }
    return {
        "path": golden.path,
        "output_path": golden.output_path,
        "kind": golden.kind,
        "body": read_capped_text(path) or "",
    }


def actual_output_state(
    output_path: str | None,
    workspace: Path,
) -> dict[str, Any] | None:
    if not output_path:
        return None
    dest = workspace / output_path
    present = dest.is_file()
    if not present:
        return {
            "path": output_path,
            "present": False,
            "body": None,
            "kind": None,
            "size": 0,
        }
    data = dest.read_bytes()
    sniffed = sniff_output_bytes(data)
    if sniffed["kind"] == "bytes":
        return {
            "path": output_path,
            "present": True,
            "body": None,
            **sniffed,
        }
    body = read_capped_text(dest)
    return {
        "path": output_path,
        "present": True,
        "body": body,
        **sniffed,
    }


def case_for_task(pack: CasePack | None, task_id: str) -> PackCase | None:
    if pack is None:
        return None
    for case in pack.cases:
        if case.id == task_id and case.status == "pinned":
            return case
    return None


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
    for item, case in zip(dumped_cases, pack.cases):
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
        # Missing expected-output files fail that check at run time.
        # Do not abort the whole suite here.


MISSING_GOLDEN_REASON = "This check is missing its expected output file."


def no_trigger_output_warning(case: PackCase) -> str | None:
    if case.should_trigger:
        return None
    if case.golden is None and not case.contains:
        return None
    return NO_TRIGGER_OUTPUT_WARNING


def task_missing_golden(root: Path, task_id: str) -> bool:
    """True when this pinned case names an expected-output file that is not on disk."""
    try:
        pack = load_case_pack(root)
    except (SuiteError, OSError, ValueError):
        return False
    case = case_for_task(pack, task_id)
    if case is None or case.golden is None or not case.should_trigger:
        return False
    return not (root / case.golden.path).is_file()


def _skill_name(root: Path) -> str:
    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        try:
            from skillgate_ai.ingest import ingest_skill

            return ingest_skill(root, strict=False).name
        except Exception:
            pass
    return root.name


def _file_copies(raw: object) -> list[CaseFileCopy]:
    if not isinstance(raw, list):
        return []
    out: list[CaseFileCopy] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        src = str(item.get("src") or "").strip()
        dest = str(item.get("dest") or Path(src).name).strip()
        if src:
            out.append(CaseFileCopy(src=src, dest=dest or Path(src).name))
    return out


def _inline_input_text(raw: dict[str, Any]) -> str | None:
    for key in ("input", "input_text"):
        value = raw.get(key)
        if isinstance(value, str):
            return value
    return None


def _case_from_check(root: Path, raw: dict[str, Any], skill_name: str) -> PackCase:
    del skill_name
    case_id = case_id_slug(str(raw.get("id") or "example"))
    should = bool(raw.get("should_trigger", True))
    judge = parse_judge_block(raw.get("judge"))
    file_items = raw.get("files") if isinstance(raw.get("files"), list) else []
    inline = _inline_input_text(raw)
    if inline is not None:
        if file_items and isinstance(file_items[0], dict):
            first = dict(file_items[0])
            first["content"] = inline
            file_items = [first, *file_items[1:]]
        else:
            file_items = [{"content": inline, "dest": f"{case_id}.txt"}]
    files = _persist_input_files(root, file_items, case_id=case_id)
    needs_upload = bool(raw.get("needs_upload"))
    output_path = str(raw.get("output_path") or "").strip() or None
    contains = raw.get("contains") or raw.get("expected")
    contains_list: list[str] = []
    if isinstance(contains, str) and contains.strip():
        contains_list = [contains.strip()]
    elif isinstance(contains, list):
        contains_list = [str(item).strip() for item in contains if str(item).strip()]
    golden: CaseGolden | None = None
    golden_path = str(raw.get("golden_path") or "").strip() or None
    if should and (output_path or golden_path):
        golden = _persist_golden(
            root,
            case_id=case_id,
            output_path=output_path,
            golden_path=golden_path,
            contains_list=contains_list,
        )
    return PackCase(
        id=case_id,
        status="pinned",
        prompt=str(raw.get("prompt") or "").strip(),
        should_trigger=should,
        input=CaseInput(files=files, needs_upload=needs_upload),
        golden=golden,
        contains=contains_list,
        min_pages=raw.get("min_pages"),
        budgets=parse_budgets(raw.get("budgets")),
        judge=judge,
    )


def _file_content(item: dict[str, Any]) -> str | bytes | None:
    for key in ("content", "text", "body"):
        if key in item:
            value = item.get(key)
            if isinstance(value, (str, bytes)):
                return value
            if value is None:
                return None
            return str(value)
    return None


def _persist_input_files(root: Path, files: object, *, case_id: str) -> list[CaseFileCopy]:
    if not isinstance(files, list):
        return []
    out: list[CaseFileCopy] = []
    for item in files:
        if not isinstance(item, dict):
            continue
        src = str(item.get("src") or "").strip()
        dest_name = str(item.get("dest") or Path(src).name).strip() or Path(src).name
        content = _file_content(item)
        if content is not None:
            name = dest_name or f"{case_id}.txt"
            if src and not Path(src).is_absolute():
                rel = safe_relpath(src)
            else:
                rel = f"{FIXTURE_DIR}/{Path(name).name}"
            written = write_pack_file(root, rel=rel, content=content)
            out.append(CaseFileCopy(src=written["src"], dest=dest_name or written["dest"]))
            continue
        if not src:
            continue
        src_path = Path(src)
        if src_path.is_absolute() and src_path.is_file():
            written = copy_into_pack(root, src=src_path, dest_name=dest_name)
            out.append(CaseFileCopy(src=written["src"], dest=written["dest"]))
            continue
        candidate = root / src
        if candidate.is_file():
            out.append(CaseFileCopy(src=safe_relpath(src), dest=dest_name))
            continue
        if src_path.is_file():
            written = copy_into_pack(root, src=src_path, dest_name=dest_name)
            out.append(CaseFileCopy(src=written["src"], dest=written["dest"]))
            continue
        raise ValueError(f"Pin could not find input file {src}.")
    return out


def _disk_golden(
    root: Path, case_id: str, output_path: str | None
) -> CaseGolden | None:
    found = resolve_golden_src(root, case_id, None)
    if found is None:
        return None
    try:
        rel = found.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None
    return CaseGolden(
        output_path=output_path or "output/result.txt",
        path=rel,
        kind=golden_kind(found),
    )


def _persist_golden(
    root: Path,
    *,
    case_id: str,
    output_path: str | None,
    golden_path: str | None,
    contains_list: list[str],
) -> CaseGolden:
    dest_output = output_path or "output/result.txt"
    found = resolve_golden_src(root, case_id, golden_path)
    if found is not None:
        try:
            rel = found.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            found = None
        else:
            if rel.startswith(f"{GOLDEN_DIR}/"):
                return CaseGolden(
                    output_path=dest_output, path=rel, kind=golden_kind(found)
                )
            suffix = found.suffix or ".txt"
            rel = f"{GOLDEN_DIR}/{case_id}{suffix}"
            write_pack_file(root, rel=rel, content=found.read_bytes())
            return CaseGolden(
                output_path=dest_output, path=rel, kind=golden_kind(found)
            )
    if not contains_list:
        raise ValueError(PIN_NEEDS_EXPECTED)
    body = contains_list[0]
    suffix = ".json" if dest_output.endswith(".json") and _JSONISH_RE.match(body) else ".txt"
    if dest_output.endswith(".json") and len(contains_list) == 1 and _JSONISH_RE.match(body):
        suffix = ".json"
    rel = f"{GOLDEN_DIR}/{case_id}{suffix}"
    text = body if body.endswith("\n") else body + "\n"
    if len(contains_list) > 1:
        text = "\n".join(contains_list) + "\n"
    write_pack_file(root, rel=rel, content=text)
    kind = "json" if suffix == ".json" else "text"
    return CaseGolden(output_path=dest_output, path=rel, kind=kind)


def _project_root_for_skill(skill_path: Path) -> Path | None:
    for candidate in (skill_path, *skill_path.parents):
        if (candidate / "evals").is_dir() and (candidate / "skills").is_dir():
            return candidate
    return None


def _bundled_suite_trust(skill_path: Path) -> TrustSuite | None:
    from skillgate_ai.suite import load_suite

    project = _project_root_for_skill(skill_path)
    if project is None:
        return None
    name = _skill_name(skill_path)
    for candidate in (
        project / "evals" / f"{name}.yaml",
        project / "evals" / f"{name}.yml",
    ):
        if not candidate.is_file():
            continue
        raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict) and raw.get("from_pack"):
            continue
        spec, _ = load_suite(candidate)
        return TrustSuite(
            fingerprint=suite_fingerprint(spec),
            case_ids=tuple(task.id for task in spec.tasks),
            source="bundled_suite",
            suite=spec,
        )
    return None


def _template_trust(_skill_path: Path) -> TrustSuite | None:
    return None
