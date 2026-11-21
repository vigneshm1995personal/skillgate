"""Author I/O pack: cases.yaml + fixtures inputs + golden outputs.

The skill directory is the only blob store. Pinned cases are the Deploy trust
path; drafts and suggest-from-skill checks are not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skillgate_ai.case_pack.models import NO_TRIGGER_OUTPUT_WARNING, CaseGolden, CasePack, PackCase
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


def dataset_view(skill_path: str | Path) -> dict[str, Any] | None:
    """Dataset listing: examples with input and expected-output previews."""
    root = Path(skill_path).expanduser().resolve()
    if not root.is_dir():
        return None
    pack = load_case_pack(root)
    if pack is None:
        from skillgate_ai.case_pack.pins import _skill_name

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
            state = golden_state(
                case.golden,
                root,
                contains=case.contains,
                output_optional=case.output_optional,
            )
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
    from skillgate_ai.case_pack.suites import pack_fingerprint

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
