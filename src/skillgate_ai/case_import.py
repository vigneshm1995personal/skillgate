"""Bulk import checks from CSV, JSONL, or YAML into evals/cases.yaml."""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from skillgate_ai.case_pack import (
    PIN_NEEDS_EXPECTED,
    PackCase,
    _inline_input_text,
    _skill_name,
    cases_path,
    expected_without_target_warning,
    load_case_pack,
    pin_checks,
)
from skillgate_ai.pack_schema import parse_judge_block
from skillgate_ai.errors import SuiteError
from skillgate_ai.pack_edit import validate_pin_judge, _short_case_id
from skillgate_ai.pack_schema import case_id_slug, case_is_locked, keep_locked_case

OnConflict = Literal["skip", "replace", "fail"]
_FORMAT_BY_SUFFIX = {
    ".csv": "csv",
    ".tsv": "csv",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".yaml": "yaml",
    ".yml": "yaml",
}
_BOOL_TRUE = frozenset({"1", "true", "yes", "y", "on"})
_BOOL_FALSE = frozenset({"0", "false", "no", "n", "off"})


@dataclass(frozen=True)
class ImportRowPreview:
    row: int
    id: str
    prompt: str
    action: Literal["add", "replace", "skip"]
    error: str | None = None


@dataclass
class ImportPlan:
    format: str
    rows: list[ImportRowPreview] = field(default_factory=list)
    checks: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(item.error for item in self.rows) and bool(self.checks)


class CaseImportError(SuiteError):
    def __init__(self, message: str, *, rows: list[ImportRowPreview] | None = None) -> None:
        super().__init__(message, exit_code=1)
        self.rows = rows or []


def detect_format(filename: str | None, content: bytes) -> str:
    name = (filename or "").lower()
    for suffix, fmt in _FORMAT_BY_SUFFIX.items():
        if name.endswith(suffix):
            return fmt
    text = content.lstrip()
    if not text:
        raise CaseImportError("Import file is empty.")
    if text[:1] in {b"[", b"{"}:
        return "jsonl" if b"\n{" in text[:4096] or text.count(b"\n") > 1 else "yaml"
    if b"\n" in text[:2048] and text.splitlines()[0].count(b",") >= 2:
        return "csv"
    try:
        yaml.safe_load(content.decode("utf-8"))
        return "yaml"
    except yaml.YAMLError:
        return "csv"


def parse_import_bytes(
    content: bytes,
    *,
    filename: str | None = None,
    format_hint: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    fmt = (format_hint or detect_format(filename, content)).lower()
    text = content.decode("utf-8-sig")
    if fmt == "csv":
        return fmt, _parse_csv(text)
    if fmt == "jsonl":
        return fmt, _parse_jsonl(text)
    if fmt == "yaml":
        return fmt, _parse_yaml(text)
    raise CaseImportError(f"Unsupported import format: {fmt}")


def plan_case_import(
    skill_path: str | Path,
    content: bytes,
    *,
    filename: str | None = None,
    format_hint: str | None = None,
    on_conflict: OnConflict = "fail",
) -> ImportPlan:
    fmt, raw_rows = parse_import_bytes(content, filename=filename, format_hint=format_hint)
    root = Path(skill_path).expanduser().resolve()
    skill_name = _skill_name(root)
    existing = load_case_pack(root) if cases_path(root).is_file() else None
    taken = {case.id for case in (existing.cases if existing else [])}
    held = {case.id: case for case in (existing.cases if existing else [])}
    previews: list[ImportRowPreview] = []
    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_import_ids: set[str] = set()

    for index, raw in enumerate(raw_rows, start=1):
        try:
            check = _normalize_import_row(raw, taken=taken, skill_name=skill_name)
        except ValueError as exc:
            previews.append(
                ImportRowPreview(row=index, id="", prompt="", action="skip", error=str(exc))
            )
            continue
        case_id = str(check.get("id") or "").strip()
        prompt = str(check.get("prompt") or "").strip()
        if case_id in seen_import_ids:
            previews.append(
                ImportRowPreview(
                    row=index,
                    id=case_id,
                    prompt=prompt,
                    action="skip",
                    error=f"Duplicate id {case_id} in this file.",
                )
            )
            continue
        seen_import_ids.add(case_id)

        action: Literal["add", "replace", "skip"] = "add"
        err: str | None = None
        if existing and case_id in taken:
            if case_is_locked(
                skill_name, case_id, pack_case_ids=taken, pack_root=root
            ):
                action = "skip"
            elif on_conflict == "fail":
                action = "skip"
                err = f"Check {case_id} already exists."
            elif on_conflict == "skip":
                action = "skip"
            else:
                action = "replace"

        if err is None and action != "skip":
            try:
                validate_pin_judge(root, [check], None, has_pack_judge=False)
                warn = _validate_check_dict(root, check, skill_name, held=held)
                if warn and warn not in warnings:
                    warnings.append(warn)
            except (SuiteError, ValueError) as exc:
                err = str(exc.message if isinstance(exc, SuiteError) else exc)

        previews.append(
            ImportRowPreview(row=index, id=case_id, prompt=prompt, action=action, error=err)
        )
        if err is None and action != "skip":
            checks.append(check)
            taken.add(case_id)

    return ImportPlan(format=fmt, rows=previews, checks=checks, warnings=warnings)


def apply_case_import(
    skill_path: str | Path,
    content: bytes,
    *,
    filename: str | None = None,
    format_hint: str | None = None,
    on_conflict: OnConflict = "fail",
    dry_run: bool = False,
) -> ImportPlan:
    plan = plan_case_import(
        skill_path,
        content,
        filename=filename,
        format_hint=format_hint,
        on_conflict=on_conflict,
    )
    if any(row.error for row in plan.rows):
        bad = [row for row in plan.rows if row.error]
        lines = [f"row {row.row}: {row.error}" for row in bad[:20]]
        extra = len(bad) - 20
        if extra > 0:
            lines.append(f"... and {extra} more row errors")
        raise CaseImportError("\n".join(lines), rows=bad)
    if dry_run or not plan.checks:
        return plan
    pin_checks(skill_path, plan.checks)
    return plan


def _parse_csv(text: str) -> list[dict[str, Any]]:
    if not text.strip():
        return []
    sample = text[:4096]
    delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if reader.fieldnames is None:
        raise CaseImportError("CSV has no header row.")
    rows: list[dict[str, Any]] = []
    for raw in reader:
        if not raw:
            continue
        cleaned = {str(k or "").strip().lower(): v for k, v in raw.items() if k}
        if not any(str(v or "").strip() for v in cleaned.values()):
            continue
        rows.append(_dict_from_flat_row(cleaned))
    if not rows:
        raise CaseImportError("No data rows found in CSV.")
    return rows


def _parse_jsonl(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise CaseImportError(f"JSONL line {line_no} is not valid JSON.") from exc
        if not isinstance(parsed, dict):
            raise CaseImportError(f"JSONL line {line_no} must be a JSON object.")
        rows.append(dict(parsed))
    if not rows:
        raise CaseImportError("No objects found in JSONL.")
    return rows


def _parse_yaml(text: str) -> list[dict[str, Any]]:
    try:
        parsed = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise CaseImportError("YAML could not be parsed.") from exc
    if isinstance(parsed, list):
        return [dict(item) for item in parsed if isinstance(item, dict)]
    if isinstance(parsed, dict):
        cases = parsed.get("cases")
        if isinstance(cases, list):
            return [dict(item) for item in cases if isinstance(item, dict)]
    raise CaseImportError("YAML must be a list of checks or a mapping with `cases:`.")


def _dict_from_flat_row(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        if value is None:
            continue
        text = str(value).strip()
        if not text:
            continue
        norm = key.replace("-", "_").lower()
        if norm in {"expected", "contains"}:
            out["contains"] = text
        elif norm in {"output", "output_path"}:
            out["output_path"] = text
        elif norm == "output_optional":
            out["output_optional"] = _parse_bool(text)
        elif norm in {"input", "input_text", "fixture", "src"}:
            out.setdefault("files", [])
            if isinstance(out["files"], list):
                for part in re.split(r"[;|]", text):
                    piece = part.strip()
                    if piece:
                        out["files"].append({"src": piece})
        elif norm == "files":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                out["files"] = [{"src": piece.strip()} for piece in text.split(";") if piece.strip()]
            else:
                out["files"] = parsed
        elif norm in {"no_trigger", "notrigger"}:
            out["should_trigger"] = not _parse_bool(text)
        elif norm == "should_trigger":
            out["should_trigger"] = _parse_bool(text)
        elif norm == "min_pages":
            out["min_pages"] = int(text)
        else:
            out[norm] = text
    return out


def _parse_bool(text: str) -> bool:
    lowered = text.strip().lower()
    if lowered in _BOOL_TRUE:
        return True
    if lowered in _BOOL_FALSE:
        return False
    raise ValueError(f"Expected true/false, got {text!r}.")


def _normalize_import_row(
    raw: dict[str, Any],
    *,
    taken: set[str],
    skill_name: str,
) -> dict[str, Any]:
    del skill_name
    row = dict(raw)
    prompt = str(row.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("Each row needs a prompt.")
    wanted = case_id_slug(str(row.get("id") or "")) if str(row.get("id") or "").strip() else ""
    case_id = wanted or _short_case_id(prompt, taken)
    row["id"] = case_id
    row["prompt"] = prompt
    if "should_trigger" not in row and row.get("no_trigger") is not None:
        row["should_trigger"] = not bool(row.get("no_trigger"))
    inline = _inline_input_text(row)
    files = row.get("files")
    if inline is not None and not files:
        row["files"] = [{"content": inline, "dest": f"{case_id}.txt"}]
    return row


def _validate_check_dict(
    root: Path,
    raw: dict[str, Any],
    skill_name: str,
    *,
    held: dict[str, Any],
) -> str | None:
    pack_ids = list(held.keys())
    if (
        keep_locked_case(skill_name, held, raw, pack_case_ids=pack_ids)
        is not None
    ):
        raise ValueError("This pack's original checks stay.")
    case_id = str(raw.get("id") or "").strip()
    should = bool(raw.get("should_trigger", True))
    output_path = str(raw.get("output_path") or "").strip() or None
    contains = raw.get("contains") or raw.get("expected")
    has_expected = bool(
        (isinstance(contains, str) and contains.strip())
        or (isinstance(contains, list) and any(str(c).strip() for c in contains))
    )
    golden_path = str(raw.get("golden_path") or "").strip() or None
    if should and output_path and not golden_path and not has_expected:
        raise ValueError(PIN_NEEDS_EXPECTED)
    if golden_path:
        candidate = root / golden_path
        if not candidate.is_file():
            raise ValueError(f"Pin could not find golden file {golden_path}.")
    file_items = raw.get("files") if isinstance(raw.get("files"), list) else []
    for item in file_items:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if isinstance(content, (str, bytes)) and str(content).strip():
            continue
        src = str(item.get("src") or "").strip()
        if not src:
            continue
        candidate = root / src
        src_path = Path(src)
        if not candidate.is_file() and not src_path.is_file():
            raise ValueError(f"Pin could not find input file {src}.")
    try:
        PackCase(
            id=case_id,
            status="pinned",
            prompt=str(raw.get("prompt") or "").strip(),
            should_trigger=should,
            contains=contains if isinstance(contains, list) else contains,
            judge=parse_judge_block(raw.get("judge")),
        )
    except ValueError as exc:
        raise ValueError(str(exc)) from exc
    return expected_without_target_warning(
        contains=str(contains or ""),
        output_path=output_path or "",
        golden_path=golden_path or "",
        should_trigger=should,
    )
