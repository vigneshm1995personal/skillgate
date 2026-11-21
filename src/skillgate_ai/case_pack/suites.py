"""Author I/O pack: cases.yaml + fixtures inputs + golden outputs.

The skill directory is the only blob store. Pinned cases are the Deploy trust
path; drafts and suggest-from-skill checks are not.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml

from skillgate_ai.case_pack.dataset import no_trigger_output_warning
from skillgate_ai.case_pack.models import (
    PACK_FINGERPRINT_FIELDS,
    PIN_NEEDS_EXPECTED,
    PIN_NEEDS_EXPECTED_HINT,
    CaseGolden,
    CaseInput,
    CasePack,
    PackCase,
    TrustSuite,
)
from skillgate_ai.case_pack.pins import _case_from_check, _file_copies, _skill_name
from skillgate_ai.case_pack.store import cases_path, load_case_pack
from skillgate_ai.errors import SuiteError
from skillgate_ai.metrics import merge_budgets, parse_budgets
from skillgate_ai.pack_files import (
    GOLDEN_TAIL_CHARS as GOLDEN_TAIL_CHARS,
)
from skillgate_ai.pack_schema import (
    ExtraQuestion as ExtraQuestion,
)
from skillgate_ai.pack_schema import (
    case_id_slug,
    case_is_locked,
    keep_locked_case,
)
from skillgate_ai.suite import DEFAULT_TASK_TIMEOUT_SEC, SuiteSpec, _normalize_suite


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
        if case.output_optional:
            dump["output_optional"] = True
            dump["contains"] = list(case.contains)
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
            if case.output_optional:
                entry = {"path": case.golden.output_path, "optional": True}
                if case.min_pages is not None:
                    entry["min_pages"] = case.min_pages
                expects.append(entry)
            elif case.contains:
                for item in case.contains:
                    entry = {
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
            if case.output_optional:
                rubric = {
                    "id": "output-exists",
                    "file": case.golden.output_path,
                    "optional": True,
                }
            else:
                rubric = {
                    "id": "output-exists",
                    "file": case.golden.output_path,
                    "min_bytes": 1,
                }
                if case.contains:
                    rubric["contains"] = case.contains[0]
            scorers.append({"type": "rubric", "min_score": 1.0, "checks": [rubric]})
        elif case.contains and case.should_trigger and not case.output_optional:
            scorers.append(
                {
                    "type": "answer_contains",
                    "answer": list(case.contains),
                }
            )
        trigger_mode = bool(case.trigger_mode) or (
            case.should_trigger and case.golden is None and not case.contains
        )
        task_raw: dict[str, Any] = {
            "id": case.id,
            "prompt": case.prompt,
            "expect_skill": pack.skill if case.should_trigger else None,
            "files": [{"src": item.src, "dest": item.dest} for item in case.input.files],
            "scorers": scorers,
            "trigger_mode": trigger_mode,
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
            "output_optional": case.output_optional,
            "bank_status": case.status,
            "locked": case_is_locked(pack.skill, case.id, pack_case_ids=[c.id for c in pack.cases]),
        }
        if case.judge is not None and not case.judge.is_empty():
            check["judge"] = case.judge.to_sparse_dict()
        warning = no_trigger_output_warning(case)
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
            if case_is_locked(existing.skill, c.id, pack_case_ids=all_ids) and c.id not in present
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
                output_optional=raw.get("output_optional", False),
            )
        )
    return pack_fingerprint(CasePack(schema_version=1, skill=skill, cases=cases))


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
