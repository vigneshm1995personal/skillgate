"""Add custom checks and extra scoring questions to a pack."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from skillgate_ai.case_pack import (
    expected_without_target_warning,
    load_case_pack,
    pin_case_ids,
    pin_checks,
    save_case_pack,
    save_pack_judge,
)
from skillgate_ai.errors import SuiteError
from skillgate_ai.judge_spec import (
    RESERVED_IDS,
    _on_fail_value,
    parse_extra_question,
    resolve_judge_spec,
)
from skillgate_ai.pack_schema import (
    SEED_EDIT_HINT,
    SEED_EDIT_MESSAGE,
    ExtraQuestion,
    JudgeBlock,
    case_id_slug,
    case_is_locked,
    merge_judge_block,
    parse_judge_block,
    parse_judge_patch,
)


def validate_pin_judge(
    skill_path: str | Path,
    checks: list[Any] | None,
    pack_judge: dict[str, Any] | None,
    *,
    has_pack_judge: bool,
) -> None:
    if isinstance(checks, list):
        for raw in checks:
            if not isinstance(raw, dict) or not raw.get("judge"):
                continue
            block = parse_judge_block(raw.get("judge"))
            if block is not None:
                resolve_judge_spec(case=block.to_sparse_dict())
    if not has_pack_judge:
        return
    incoming, removed = parse_judge_patch(pack_judge)
    loaded = load_case_pack(skill_path)
    existing = loaded.judge if loaded is not None else None
    merged = merge_judge_block(existing, incoming, removed_ids=removed)
    if merged is not None:
        resolve_judge_spec(pack=merged.to_sparse_dict())


def apply_pin(
    skill_path: str | Path,
    *,
    checks: list[Any] | None = None,
    case_ids: list[Any] | None = None,
    pack_judge: dict[str, Any] | None = None,
    has_pack_judge: bool = False,
) -> tuple[Any, list[str]]:
    validate_pin_judge(
        skill_path,
        checks if isinstance(checks, list) else None,
        pack_judge if isinstance(pack_judge, dict) else None,
        has_pack_judge=has_pack_judge,
    )
    warnings: list[str] = []
    pack = None
    if isinstance(checks, list) and checks:
        for raw in checks:
            if not isinstance(raw, dict):
                continue
            warn = expected_without_target_warning(
                contains=str(raw.get("contains") or raw.get("expected") or ""),
                output_path=str(raw.get("output_path") or ""),
                golden_path=str(raw.get("golden_path") or ""),
                should_trigger=bool(raw.get("should_trigger", True)),
            )
            if warn and warn not in warnings:
                warnings.append(warn)
        pack = pin_checks(skill_path, [dict(item) for item in checks])
    elif isinstance(case_ids, list) and case_ids:
        pack = pin_case_ids(skill_path, [str(item) for item in case_ids])
    else:
        raise SuiteError("Pin needs checks or case ids.")
    if has_pack_judge:
        pack = save_pack_judge(skill_path, pack_judge)
    return pack, warnings


def remove_pack_case(skill_path: str | Path, case_id: str):
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise SuiteError("This skill has no case pack yet.")
    wanted = case_id_slug(case_id)
    pack_ids = [case.id for case in pack.cases]
    if case_is_locked(pack.skill, wanted, pack_case_ids=pack_ids):
        raise SuiteError(
            "This pack's original checks stay. Add a new check instead of deleting them."
        )
    kept = [case for case in pack.cases if case.id != wanted]
    if len(kept) == len(pack.cases):
        raise SuiteError(f"No check named {wanted}.")
    updated = pack.model_copy(update={"cases": kept})
    save_case_pack(root, updated)
    return updated


def edit_pack_case(
    skill_path: str | Path,
    case_id: str,
    *,
    prompt: str | None = None,
    expected: str | None = None,
    output_path: str | None = None,
    output_optional: bool | None = None,
):
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise SuiteError("This skill has no case pack yet.")
    case_id = case_id_slug(case_id)
    pack_ids = [case.id for case in pack.cases]
    if case_is_locked(pack.skill, case_id, pack_case_ids=pack_ids):
        raise SuiteError(SEED_EDIT_MESSAGE, hint=SEED_EDIT_HINT)
    found = False
    cases = []
    for case in pack.cases:
        if case.id != case_id:
            cases.append(case)
            continue
        found = True
        updates: dict[str, Any] = {}
        if prompt is not None:
            updates["prompt"] = prompt
        if expected is not None:
            updates["contains"] = [expected] if expected.strip() else []
        if output_path is not None and case.golden is not None:
            updates["golden"] = case.golden.model_copy(update={"output_path": output_path})
        if output_optional is not None:
            updates["output_optional"] = bool(output_optional)
        cases.append(case.model_copy(update=updates) if updates else case)
    if not found:
        raise SuiteError(f"No check named {case_id}.")
    updated = pack.model_copy(update={"cases": cases})
    save_case_pack(root, updated)
    return updated


def bind_case_files(
    skill_path: str | Path,
    *,
    inherit: bool = True,
    expand: bool = False,
    glob_pat: str | None = None,
):
    from skillgate_ai.case_pack import checks_from_pack
    from skillgate_ai.fixture_bind import apply_inherit, expand_from_folder

    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise SuiteError("This skill has no case pack yet.")
    checks = checks_from_pack(pack, include_drafts=True)
    if expand:
        bound = expand_from_folder(root, checks, glob_pat=glob_pat)
    else:
        bound = apply_inherit(root, checks, inherit=inherit, glob_pat=glob_pat)
    return pin_checks(root, bound)


def add_judge_question(
    skill_path: str | Path,
    *,
    ask: str,
    kind: str = "predicate",
    question_id: str | None = None,
    on_fail: str = "block",
    choices: list[str] | None = None,
):
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise SuiteError("This skill has no case pack yet.")
    qid = (question_id or "").strip() or _question_id(ask)
    raw: dict[str, Any] = {
        "id": qid,
        "type": kind,
        "ask": ask,
        "on_fail": on_fail,
        "pass_if": {"gte": 0.8} if kind.lower() in {"predicate", "yes/no"} else None,
    }
    if choices:
        raw["choices"] = list(choices)
    parsed = parse_extra_question(raw)
    extra = ExtraQuestion(
        id=parsed.id,
        type=parsed.type,  # type: ignore[arg-type]
        ask=parsed.ask,
        on_fail=parsed.on_fail,  # type: ignore[arg-type]
        choices=list(parsed.choices) or None,
        levels=list(parsed.levels) or None,
        pass_if=parsed.pass_if,
        include_when=parsed.include_when,
    )
    current = pack.judge or JudgeBlock()
    extras = [*current.extra_questions, extra]
    updated_block = current.model_copy(update={"extra_questions": extras})
    resolve_judge_spec(pack=updated_block.to_sparse_dict())
    return save_pack_judge(root, updated_block.to_sparse_dict())


def set_question_on_fail(skill_path: str | Path, question_id: str, on_fail: str):
    mapped = _on_fail_value(on_fail, default="block")
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise SuiteError("This skill has no case pack yet.")
    current = pack.judge or JudgeBlock()
    if question_id in RESERVED_IDS:
        on_fail_map = dict(current.on_fail or {})
        on_fail_map[question_id] = mapped
        updated = current.model_copy(update={"on_fail": on_fail_map})
    else:
        extras = []
        found = False
        for item in current.extra_questions:
            if item.id == question_id:
                found = True
                extras.append(item.model_copy(update={"on_fail": mapped}))
            else:
                extras.append(item)
        if not found:
            raise SuiteError(f"No question named {question_id}.")
        updated = current.model_copy(update={"extra_questions": extras})
    resolve_judge_spec(pack=updated.to_sparse_dict())
    return save_pack_judge(root, updated.to_sparse_dict())


def remove_judge_question(skill_path: str | Path, question_id: str):
    qid = question_id.strip()
    if qid in RESERVED_IDS:
        raise SuiteError("Skill Gate’s questions stay. Remove an extra question instead.")
    pack = load_case_pack(skill_path)
    extras = list(pack.judge.extra_questions) if pack and pack.judge else []
    if qid not in {item.id for item in extras}:
        raise SuiteError(f"No question named {qid}.")
    return save_pack_judge(skill_path, {"removed_extra_ids": [qid]})


def add_pack_case(
    skill_path: str | Path,
    *,
    prompt: str,
    case_id: str | None = None,
    expected: str | None = None,
    output_path: str | None = None,
    should_trigger: bool = True,
    files: list[dict[str, Any]] | None = None,
    inputs: list[str] | None = None,
    force: bool = False,
    output_optional: bool = False,
):
    if not str(prompt or "").strip():
        raise SuiteError("Add a prompt for this check.")
    file_rows = list(files or [])
    for raw in inputs or []:
        src = str(raw).strip()
        if src:
            file_rows.append({"src": src})
    loaded = load_case_pack(skill_path)
    taken = {case.id for case in (loaded.cases if loaded else [])}
    wanted = case_id_slug(case_id) if str(case_id or "").strip() else ""
    if wanted and loaded and case_is_locked(
        loaded.skill, wanted, pack_case_ids=[c.id for c in loaded.cases]
    ):
        raise SuiteError(SEED_EDIT_MESSAGE, hint=SEED_EDIT_HINT)
    if wanted and wanted in taken and not force:
        raise SuiteError(f"Check {wanted} already exists. Pass --force to replace it.")
    check: dict[str, Any] = {
        "id": wanted or _short_case_id(prompt, taken),
        "prompt": prompt,
        "should_trigger": should_trigger,
        "files": file_rows,
    }
    if expected:
        check["contains"] = expected
    if output_path:
        check["output_path"] = output_path
    if output_optional:
        check["output_optional"] = True
    return pin_checks(skill_path, [check]), None


def _short_case_id(prompt: str, taken: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.strip().lower()).strip("-")
    parts = [part for part in slug.split("-") if part][:4]
    base = "-".join(parts) or "case"
    if len(base) > 40:
        base = base[:40].rstrip("-") or "case"
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


def tryout_checks(skill_path: str | Path, case_id: str) -> list[dict[str, Any]]:
    from skillgate_ai.case_pack import checks_from_pack

    pack = load_case_pack(skill_path)
    if pack is None:
        raise SuiteError("This skill has no checks yet.")
    wanted = case_id_slug(case_id)
    rows = [row for row in checks_from_pack(pack, include_drafts=True) if row.get("id") == wanted]
    if not rows:
        raise SuiteError(f"No check named {wanted}.")
    return rows


def _question_id(ask: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", ask.strip().lower()).strip("_")[:64]
    return slug or "extra"
