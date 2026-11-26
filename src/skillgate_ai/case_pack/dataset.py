"""Author I/O pack: cases.yaml + fixtures inputs + golden outputs.

The skill directory is the only blob store. Pinned cases are the Deploy trust
path; drafts and suggest-from-skill checks are not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skillgate_ai.case_pack.models import (
    NO_TRIGGER_OUTPUT_WARNING,
    CaseGolden,
    CasePack,
    PackCase,
)
from skillgate_ai.case_pack.store import load_case_pack
from skillgate_ai.errors import SuiteError
from skillgate_ai.pack import (
    pack_preview,
)
from skillgate_ai.pack_files import (
    GOLDEN_TAIL_CHARS as GOLDEN_TAIL_CHARS,
)
from skillgate_ai.pack_files import (
    read_capped_text,
    sniff_output_bytes,
)
from skillgate_ai.pack_schema import (
    ExtraQuestion as ExtraQuestion,
)
from skillgate_ai.pack_schema import (
    case_id_slug,
    case_is_locked,
)
from skillgate_ai.paths import skill_pack_root
from skillgate_ai.tool_check_schema import merge_tool_checks


def _strip_preview_text(entry: dict[str, Any]) -> dict[str, Any]:
    entry.pop("text", None)
    return entry


def _case_entry(
    root: Path, pack: CasePack, case: PackCase, *, include_files: bool
) -> dict[str, Any]:
    fixtures: list[dict[str, Any]] = []
    for item in case.input.files:
        entry = _preview_file(root, item.src)
        entry["src"] = item.src
        entry["dest"] = item.dest
        if not include_files:
            _strip_preview_text(entry)
        fixtures.append(entry)
    golden_payload: dict[str, Any] | None = None
    if case.golden:
        golden_payload = _preview_file(root, case.golden.path)
        golden_payload["output_path"] = case.golden.output_path
        golden_payload["kind"] = case.golden.kind
        if include_files:
            state = golden_state(
                case.golden,
                root,
                contains=case.contains,
                output_optional=case.output_optional,
            )
            if state and state.get("body") is not None:
                golden_payload["body"] = state["body"]
                golden_payload.setdefault("text", state["body"])
        else:
            _strip_preview_text(golden_payload)
    case_tool = (
        case.tool_checks.to_sparse_dict()
        if case.tool_checks and not case.tool_checks.is_empty()
        else None
    )
    row: dict[str, Any] = {
        "id": case.id,
        "status": case.status,
        "prompt": case.prompt,
        "should_trigger": case.should_trigger,
        "output_optional": case.output_optional,
        "tool_checks": case_tool,
        "fixtures": fixtures,
        "golden": golden_payload,
    }
    if not include_files:
        row["has_expected"] = bool(case.contains)
    return row


def dataset_view(skill_path: str | Path, *, include_files: bool = True) -> dict[str, Any] | None:
    """Dataset listing: examples with input and expected-output previews."""
    root = skill_pack_root(skill_path)
    if not root.is_dir():
        return None
    pack = load_case_pack(root)
    if pack is None:
        from skillgate_ai.case_pack.pins import _skill_name

        return {
            "skill": _skill_name(root),
            "fingerprint": None,
            "tool_checks": None,
            "files_included": include_files,
            "cases": [],
        }
    from skillgate_ai.case_pack.suites import pack_fingerprint

    pack_tool = (
        pack.tool_checks.to_sparse_dict()
        if pack.tool_checks and not pack.tool_checks.is_empty()
        else None
    )
    cases = [_case_entry(root, pack, case, include_files=include_files) for case in pack.cases]
    return {
        "skill": pack.skill,
        "fingerprint": pack_fingerprint(pack),
        "tool_checks": pack_tool,
        "files_included": include_files,
        "cases": cases,
    }


def case_view(skill_path: str | Path, case_id: str) -> dict[str, Any] | None:
    """Full single case: file bodies, expected-output state, tool_checks (case + effective)."""
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        return None
    wanted = case_id_slug(case_id)
    case = next((c for c in pack.cases if c.id == wanted), None)
    if case is None:
        return None
    entry = _case_entry(root, pack, case, include_files=True)
    entry["contains"] = list(case.contains)
    entry["expected"] = golden_state(
        case.golden,
        root,
        contains=case.contains,
        output_optional=case.output_optional,
    )
    entry["min_pages"] = case.min_pages
    entry["locked"] = case_is_locked(pack.skill, case.id, pack_case_ids=[c.id for c in pack.cases])
    entry["judge"] = (
        case.judge.to_sparse_dict() if case.judge and not case.judge.is_empty() else None
    )
    entry["budgets"] = (
        case.budgets.to_sparse_dict() if case.budgets and not case.budgets.is_empty() else None
    )
    merged = merge_tool_checks(
        pack.tool_checks, case.tool_checks, should_trigger=case.should_trigger
    )
    entry["effective_tool_checks"] = (
        merged.model_dump(exclude_defaults=True) if merged is not None else None
    )
    entry["warning"] = no_trigger_output_warning(case)
    from skillgate_ai.case_pack.suites import pack_fingerprint

    pack_tool = (
        pack.tool_checks.to_sparse_dict()
        if pack.tool_checks and not pack.tool_checks.is_empty()
        else None
    )
    return {
        "skill": pack.skill,
        "fingerprint": pack_fingerprint(pack),
        "pack_tool_checks": pack_tool,
        "case": entry,
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


_OPTIONAL_OUTPUT_NOTE = (
    "Example of an acceptable answer, not a required substring. "
    "A missing or empty output file is acceptable. "
    "Grade against the case prompt and the checks."
)


def golden_state(
    golden: CaseGolden | None,
    skill_root: Path,
    *,
    contains: list[str] | None = None,
    output_optional: bool = False,
) -> dict[str, Any] | None:
    needles = [str(item).strip() for item in (contains or []) if str(item).strip()]
    if golden is None:
        if not (output_optional and needles):
            return None
        return {
            "path": None,
            "output_path": None,
            "kind": "text",
            "body": needles[0],
            "output_optional": True,
            "note": _OPTIONAL_OUTPUT_NOTE,
        }
    path = skill_root / golden.path
    if golden.kind == "bytes":
        payload: dict[str, Any] = {
            "path": golden.path,
            "output_path": golden.output_path,
            "kind": golden.kind,
            "body": None,
            "note": "binary golden; compare path presence only",
        }
    else:
        payload = {
            "path": golden.path,
            "output_path": golden.output_path,
            "kind": golden.kind,
            "body": read_capped_text(path) or "",
        }
    if output_optional:
        payload["output_optional"] = True
        if needles:
            payload["body"] = needles[0]
        payload["note"] = _OPTIONAL_OUTPUT_NOTE
        return payload
    if needles:
        payload["match"] = "contains"
        payload["contains"] = needles
        payload["note"] = (
            "Required substring — the actual output must include this text; "
            "it does not need to equal the whole file. "
            "Other details in this example are not required unless the case marks them required."
        )
    else:
        payload["note"] = (
            "Example of an acceptable answer, not a full specification. "
            "Grade against the case prompt and the checks. "
            "Treat details in this example as required only when the case marks them required."
        )
    return payload


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
    from skillgate_ai.judge_context import enrich_output_row

    row: dict[str, Any] = {
        "path": output_path,
        "present": True,
        "body": None if sniffed["kind"] == "bytes" else read_capped_text(dest),
        **sniffed,
    }
    return enrich_output_row(row, dest)


def case_for_task(pack: CasePack | None, task_id: str) -> PackCase | None:
    if pack is None:
        return None
    for case in pack.cases:
        if case.id == task_id and case.status == "pinned":
            return case
    return None


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
