"""Author I/O pack: cases.yaml + fixtures inputs + golden outputs.

The skill directory is the only blob store. Pinned cases are the Deploy trust
path; drafts and suggest-from-skill checks are not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from skillgate_ai.case_pack.models import (
    _JSONISH_RE,
    PIN_NEEDS_EXPECTED,
    CaseFileCopy,
    CaseGolden,
    CaseInput,
    CasePack,
    PackCase,
    _reject_missing_seed_cases,
)
from skillgate_ai.case_pack.store import cases_path, load_case_pack, save_case_pack
from skillgate_ai.errors import SkillGateError
from skillgate_ai.metrics import parse_budgets
from skillgate_ai.pack import (
    FIXTURE_DIR,
    GOLDEN_DIR,
    copy_into_pack,
    safe_relpath,
    write_pack_file,
)
from skillgate_ai.pack_files import (
    GOLDEN_TAIL_CHARS as GOLDEN_TAIL_CHARS,
)
from skillgate_ai.pack_files import (
    golden_kind,
    resolve_golden_src,
)
from skillgate_ai.pack_schema import (
    ExtraQuestion as ExtraQuestion,
)
from skillgate_ai.pack_schema import (
    case_id_slug,
    keep_locked_case,
    parse_judge_block,
)
from skillgate_ai.paths import PathTraversalError, contained_path, require_under


def pin_checks(skill_path: str | Path, checks: list[dict[str, Any]]) -> CasePack:
    """Upsert checks into evals/cases.yaml as pinned cases."""
    root = contained_path(Path(skill_path).expanduser().resolve())
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
        schema=1,
        skill=skill_name,
        cases=list(by_id.values()),
        budgets=existing.budgets if existing else None,
        judge=existing.judge if existing else None,
        tool_checks=existing.tool_checks if existing else None,
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
                updated.append(case.model_copy(update={"status": "pinned", "golden": attached}))
                continue
            updated.append(case.model_copy(update={"status": "pinned"}))
        else:
            updated.append(case)
    missing = sorted(wanted - found)
    if missing:
        raise ValueError(f"Unknown case ids: {', '.join(missing)}")
    out = CasePack(
        schema=1,
        skill=pack.skill,
        cases=updated,
        budgets=pack.budgets,
        judge=pack.judge,
        tool_checks=pack.tool_checks,
    )
    save_case_pack(root, out)
    return out


def _skill_name(root: Path) -> str:
    skill_md = root / "SKILL.md"
    if skill_md.is_file():
        try:
            from skillgate_ai.ingest import ingest_skill

            return ingest_skill(root, strict=False).name
        except (SkillGateError, OSError, ValueError):
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
    from skillgate_ai.tool_check_schema import parse_tool_checks_block

    tool_checks = parse_tool_checks_block(raw.get("tool_checks"), level="case")
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
        tool_checks=tool_checks,
        output_optional=raw.get("output_optional", False),
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
            safe_src = require_under(root, src_path)
            written = copy_into_pack(root, src=safe_src, dest_name=dest_name)
            out.append(CaseFileCopy(src=written["src"], dest=written["dest"]))
            continue
        try:
            candidate = contained_path(root, src)
        except (ValueError, PathTraversalError):
            candidate = root / "__missing__"
        if candidate.is_file():
            out.append(CaseFileCopy(src=safe_relpath(src), dest=dest_name))
            continue
        if src_path.is_file():
            safe_src = require_under(root, src_path)
            written = copy_into_pack(root, src=safe_src, dest_name=dest_name)
            out.append(CaseFileCopy(src=written["src"], dest=written["dest"]))
            continue
        raise ValueError(f"Pin could not find input file {src}.")
    return out


def _disk_golden(root: Path, case_id: str, output_path: str | None) -> CaseGolden | None:
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
                return CaseGolden(output_path=dest_output, path=rel, kind=golden_kind(found))
            suffix = found.suffix or ".txt"
            rel = f"{GOLDEN_DIR}/{case_id}{suffix}"
            write_pack_file(root, rel=rel, content=found.read_bytes())
            return CaseGolden(output_path=dest_output, path=rel, kind=golden_kind(found))
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
    kind: Literal["json", "text"] = "json" if suffix == ".json" else "text"
    return CaseGolden(output_path=dest_output, path=rel, kind=kind)
