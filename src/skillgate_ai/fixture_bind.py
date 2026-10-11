"""Pack-as-dataset bind: inherit fixtures, authenticity, gate decision.

OSS has a local setup wizard (`skillgate ui`). Generated-check drafts and
regression stay in the private hosted app.

"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skillgate_ai.pack import (
    CASE_SUFFIXES,
    is_authentic_fixture_bytes,
    relevant_eval_fixtures,
    resolve_input_file,
)

EXPAND_CAP = 20
MISSING_FILE_CLAUSE = "needs a file in the skill folder"
DEFAULT_OUTPUT_PATH = "output/result.txt"

_FILENAME_IN_PROMPT = re.compile(
    r"\b[\w.-]+\.(?:pdf|png|jpe?g|gif|webp|csv|json|txt)\b",
    re.IGNORECASE,
)


def is_negative_check(check: dict[str, Any]) -> bool:
    return check.get("should_trigger") is False


def is_completion_check(check: dict[str, Any]) -> bool:
    item = dict(check)
    contains = str(item.get("contains") or item.get("expected") or "").strip()
    output_path = str(item.get("output_path") or "").strip()
    golden_path = str(item.get("golden_path") or "").strip()
    return bool(output_path or contains or golden_path)


def is_trigger_only(check: dict[str, Any]) -> bool:
    return not is_negative_check(check) and not is_completion_check(check)


def file_copies(fixtures: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [{"src": item["src"], "dest": item["dest"]} for item in fixtures]


def apply_inherit(
    skill_path: str | Path | None,
    checks: list[dict[str, Any]] | None,
    *,
    inherit: bool = True,
    glob_pat: str | None = None,
    promote: bool = False,
    description: str = "",
) -> list[dict[str, Any]]:
    del promote, description
    out = [dict(item) for item in (checks or [])]
    defaults = file_copies(relevant_eval_fixtures(skill_path or "", glob_pat))
    if not inherit or not defaults:
        return out
    for item in out:
        if is_negative_check(item) or is_trigger_only(item):
            continue
        if not is_completion_check(item):
            continue
        if _has_files(item.get("files")):
            item["needs_upload"] = False
            continue
        item["files"] = [dict(copy) for copy in defaults]
        item["needs_upload"] = False
    return out


def expand_from_folder(
    skill_path: str | Path | None,
    checks: list[dict[str, Any]] | None,
    *,
    glob_pat: str | None = None,
    description: str = "",
) -> list[dict[str, Any]]:
    existing = [dict(item) for item in (checks or [])]
    fixtures = relevant_eval_fixtures(skill_path or "", glob_pat)[:EXPAND_CAP]
    if not fixtures:
        return existing
    template = _template_check(existing, description)
    kept_triggers = [item for item in existing if is_trigger_only(item)]
    negatives = [item for item in existing if is_negative_check(item)]
    created: list[dict[str, Any]] = []
    used_ids = {str(item.get("id") or "") for item in kept_triggers + negatives}
    for fixture in fixtures:
        dest = fixture["dest"]
        check_id = _unique_id(f"complete-{Path(dest).stem}", used_ids)
        used_ids.add(check_id)
        created.append(
            {
                "id": check_id,
                "prompt": _prompt_for_file(str(template.get("prompt") or ""), dest),
                "should_trigger": True,
                "output_path": template.get("output_path") or DEFAULT_OUTPUT_PATH,
                "contains": template.get("contains"),
                "files": [{"src": fixture["src"], "dest": dest}],
                "needs_upload": False,
            }
        )
    return created + kept_triggers + negatives


def coverage_required(
    skill_path: str | Path | None,
    *,
    checks: list[dict[str, Any]] | None = None,
    report: dict[str, Any] | None = None,
) -> bool:
    if skill_path and relevant_eval_fixtures(skill_path):
        return True
    for item in checks or []:
        if item.get("needs_upload") or _has_files(item.get("files")):
            return True
    for task in (report or {}).get("tasks") or []:
        if not isinstance(task, dict):
            continue
        if _has_files(task.get("files")):
            return True
    return False


def authentic_completion_passed(
    skill_path: str | Path | None,
    report: dict[str, Any] | None,
) -> bool:
    for task in (report or {}).get("tasks") or []:
        if not isinstance(task, dict) or task.get("passed") is not True:
            continue
        completion_ok = False
        for score in task.get("scores") or []:
            if not isinstance(score, dict):
                continue
            if score.get("scorer") == "task_completion" and score.get("passed") is True:
                completion_ok = True
                break
        if not completion_ok:
            continue
        if _authentic_files_on_disk(skill_path, task.get("files")):
            return True
    return False


@dataclass(frozen=True)
class GateVerdict:
    decision: str
    reason: str
    warnings: tuple[str, ...] = ()


def decide_gate(
    *,
    harness: str | None,
    passed: bool | None,
    status: str | None = "done",
    skill_path: str | Path | None = None,
    report: dict[str, Any] | None = None,
    checks: list[dict[str, Any]] | None = None,
) -> str:
    return decide_gate_result(
        harness=harness,
        passed=passed,
        status=status,
        skill_path=skill_path,
        report=report,
        checks=checks,
    ).decision


def decide_gate_result(
    *,
    harness: str | None,
    passed: bool | None,
    status: str | None = "done",
    skill_path: str | Path | None = None,
    report: dict[str, Any] | None = None,
    checks: list[dict[str, Any]] | None = None,
) -> GateVerdict:
    from skillgate_ai.harness import is_live_harness

    if status == "running":
        return GateVerdict("pending", "Evaluation is still running.")
    if status == "error":
        return GateVerdict("blocked", "This run ended in error.")
    if not is_live_harness(harness):
        return GateVerdict("blocked", "Deploy needs a live harness.")
    if not passed:
        return GateVerdict("blocked", "Get a passing run to unlock Install.")
    return GateVerdict(
        "cleared",
        "This Dataset passed.",
        _pass_warnings(skill_path, report, checks),
    )


def _pass_warnings(
    skill_path: str | Path | None,
    report: dict[str, Any] | None,
    checks: list[dict[str, Any]] | None,
) -> tuple[str, ...]:
    from skillgate_ai.case_pack import trust_suite_for_skill
    from skillgate_ai.metrics import budget_gate_reason, metrics_blocking

    warnings: list[str] = []
    if coverage_required(skill_path, checks=checks, report=report) and not authentic_completion_passed(
        skill_path, report
    ):
        warnings.append("Completion coverage is required.")
    trust = trust_suite_for_skill(skill_path) if skill_path else None
    if trust is None:
        warnings.append("This skill has no Dataset.")
    else:
        run_fp = str((report or {}).get("pack_fingerprint") or "").strip() or None
        if run_fp != trust.fingerprint:
            warnings.append("This run used generated drafts, not this Dataset.")
        if not _report_covers_pinned_ids(report, trust.case_ids):
            warnings.append("This run did not cover this Dataset.")
    if metrics_blocking(report):
        warnings.append(budget_gate_reason(report))
    return tuple(warnings)


def _report_covers_pinned_ids(
    report: dict[str, Any] | None, case_ids: tuple[str, ...]
) -> bool:
    if not case_ids:
        return False
    tasks = (report or {}).get("tasks") or []
    seen = {
        str(task.get("id") or "")
        for task in tasks
        if isinstance(task, dict)
    }
    return all(case_id in seen for case_id in case_ids)


def _template_check(
    checks: list[dict[str, Any]], description: str
) -> dict[str, Any]:
    for item in checks:
        if is_completion_check(item):
            return dict(item)
    for item in checks:
        if not is_negative_check(item):
            template = dict(item)
            template["output_path"] = template.get("output_path") or DEFAULT_OUTPUT_PATH
            template["contains"] = template.get("contains")
            return template
    return {
        "prompt": f"Read the input and save the result to {DEFAULT_OUTPUT_PATH}.",
        "should_trigger": True,
        "output_path": DEFAULT_OUTPUT_PATH,
        "contains": description.strip()[:80] or None,
    }


def _prompt_for_file(template: str, dest: str) -> str:
    text = " ".join((template or "").split()).strip()
    if dest.lower() in text.lower():
        return text
    swapped = _FILENAME_IN_PROMPT.sub(dest, text, count=1)
    if swapped != text:
        return swapped
    if text:
        rest = text[0].lower() + text[1:] if text and text[0].isupper() else text
        combined = f"Read {dest}, {rest}"
    else:
        combined = f"Read {dest} and save the result to {DEFAULT_OUTPUT_PATH}."
    combined = " ".join(combined.split()).strip()
    if combined and combined[-1] not in ".!?":
        combined += "."
    if combined and combined[0].islower():
        combined = combined[0].upper() + combined[1:]
    return combined


def _authentic_files_on_disk(skill_path: str | Path | None, files: Any) -> bool:
    if not _has_files(files):
        return False
    for item in files:
        if not isinstance(item, dict):
            return False
        src = str(item.get("src") or "").strip()
        dest = str(item.get("dest") or "").strip()
        if not src or not dest:
            return False
        if Path(src).suffix.lower() in CASE_SUFFIXES:
            return False
        resolved = resolve_input_file(src, skill_root=Path(skill_path) if skill_path else None)
        if resolved is None or not resolved.is_file():
            return False
        if not is_authentic_fixture_bytes(src, resolved.read_bytes()):
            return False
    return True


def _has_files(files: Any) -> bool:
    if not isinstance(files, list) or not files:
        return False
    for item in files:
        if not isinstance(item, dict):
            continue
        src = str(item.get("src") or "").strip()
        dest = str(item.get("dest") or "").strip()
        if src and dest:
            return True
    return False


def _unique_id(base: str, used: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", base.strip().lower()).strip("-") or "complete"
    if slug not in used:
        return slug
    n = 2
    while f"{slug}-{n}" in used:
        n += 1
    return f"{slug}-{n}"
