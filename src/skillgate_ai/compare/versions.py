"""Compare runs: models (live arms) and versions (history / git)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from skillgate_ai.compare.core import (
    ALLOWED_COMPARE_HARNESS,
    CompareArmSpec,
    CompareError,
    CompareResult,
    _arm_ids,
    _as_float,
    _as_int,
    _blank,
    _resolve_compare_case_ids,
    arm_label_defaults,
)
from skillgate_ai.compare.models import _append_compare_failure, run_models_compare
from skillgate_ai.compare.payload import (
    _arm_stats_from_report,
    _build_cases,
    _case_ids_from_report,
    _skill_pack_hash_from_report,
    _usage_from_report,
)
from skillgate_ai.history import append_compare, load_history


def _history_report(pack: Path, run_id: str) -> dict[str, Any]:
    for row in load_history(pack, limit=0):
        if row.get("run_id") == run_id:
            report = row.get("report")
            if isinstance(report, dict):
                return report
            raise CompareError(f"Run {run_id} has no report.")
    raise CompareError(f"Unknown run {run_id}.")


def preflight_versions_compare(
    pack: Path,
    *,
    run_ids: list[str] | None = None,
    git_refs: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """Validate versions compare inputs before printing started or spawning work."""
    pack = pack.expanduser().resolve()
    if git_refs and len(git_refs) >= 2:
        if len(git_refs) != 2:
            raise CompareError("Pick exactly two git refs.", hint="Use --git twice.")
        if not dry_run:
            from skillgate_ai.compare_git import find_git_root

            find_git_root(pack)
        return
    if dry_run:
        ids = [str(item).strip() for item in (run_ids or []) if str(item).strip()]
        refs = [str(item).strip() for item in (git_refs or []) if str(item).strip()]
        if len(ids) < 2 and len(refs) < 2:
            return
    ids = [str(item).strip() for item in (run_ids or []) if str(item).strip()]
    if len(ids) >= 2:
        if ids[0] == ids[1]:
            raise CompareError(
                "Pick two different history runs.",
                hint="Use two distinct run ids from `skillgate history`.",
            )
        if not dry_run:
            for rid in ids[:2]:
                _history_report(pack, rid)
        return
    recent = [
        str(row.get("run_id") or "") for row in load_history(pack, limit=8) if row.get("run_id")
    ]
    hint = f"Recent runs: {', '.join(recent)}" if recent else "Use --run twice or --git twice."
    raise CompareError("Pick two history runs or two git refs.", hint=hint)


def _git_ref_picker_suggestions(pack: Path) -> list[str]:
    from skillgate_ai.compare_git import list_skill_git_versions

    return [row["ref"] for row in list_skill_git_versions(pack)]


def _versions_dry_run_payload(
    pack: Path,
    *,
    compare_id: str,
    run_ids: list[str] | None,
    git_refs: list[str] | None,
) -> dict[str, Any]:
    case_ids: list[str] = []
    arms: list[dict[str, Any]] = []
    picker: dict[str, Any] | None = None
    if run_ids and len(run_ids) >= 2:
        for idx, rid in enumerate(run_ids[:2]):
            arm_id = _arm_ids(2)[idx]
            arms.append(
                {
                    "arm_id": arm_id,
                    "label": f"Run {rid[:6]}",
                    "subtitle": "history",
                    "source": "plan",
                    "passed_count": None,
                    "task_count": None,
                    "usage": None,
                    "duration_sec": None,
                }
            )
        try:
            report = _history_report(pack, run_ids[0])
            case_ids = _case_ids_from_report(report)
            for arm in arms:
                arm["task_count"] = len(case_ids)
        except CompareError:
            pass
    elif git_refs and len(git_refs) >= 2:
        for idx, ref in enumerate(git_refs[:2]):
            arm_id = _arm_ids(2)[idx]
            arms.append(
                {
                    "arm_id": arm_id,
                    "label": ref[:12],
                    "subtitle": ref,
                    "source": "plan",
                    "passed_count": None,
                    "task_count": None,
                    "usage": None,
                    "duration_sec": None,
                }
            )
        case_ids = _resolve_compare_case_ids(pack, None)
        for arm in arms:
            arm["task_count"] = len(case_ids)
    else:
        recent = [
            str(row.get("run_id") or "") for row in load_history(pack, limit=8) if row.get("run_id")
        ]
        picker = {
            "recent_runs": recent,
            "git_refs": _git_ref_picker_suggestions(pack),
        }
    return {
        "kind": "compare",
        "compare_id": compare_id,
        "mode": "versions",
        "skill": pack.name,
        "pack_fingerprint": None,
        "pack_case_ids": case_ids,
        "status": "dry_run",
        "arms": arms,
        "cases": [
            {
                "case_id": cid,
                "results": {arm["arm_id"]: {"passed": None} for arm in arms},
                "disagreement": False,
            }
            for cid in case_ids
        ],
        "spend": {"cap_usd": None, "spent_usd": None, "stopped_reason": None},
        "error": None,
        "picker": picker,
    }


def harness_from_history(pack: Path) -> str:
    """Resolved harness from the newest history run, or ``auto``."""
    rows = load_history(pack, limit=30)
    for row in reversed(rows):
        report = row.get("report") if isinstance(row.get("report"), dict) else {}
        cfg = row.get("config") if isinstance(row.get("config"), dict) else {}
        for candidate in (report.get("harness"), cfg.get("harness"), cfg.get("harness_pref")):
            name = str(candidate or "").strip().lower()
            if name in {"cursor", "agent"}:
                return "cursor-agent"
            if name == "claude-code":
                return "claude"
            if name in ALLOWED_COMPARE_HARNESS and name != "auto":
                return name
    return "auto"


def _normalize_compare_harness(name: str | None) -> str:
    raw = (name or "").strip().lower()
    if raw in {"cursor", "agent"}:
        return "cursor-agent"
    if raw == "claude-code":
        return "claude"
    if raw in ALLOWED_COMPARE_HARNESS:
        return raw
    return ""


def run_versions_compare(
    pack: Path,
    *,
    run_ids: list[str] | None = None,
    git_refs: list[str] | None = None,
    root: Path,
    rerun: bool = False,
    compare_id: str | None = None,
    run_check_fn: Callable[..., Any] | None = None,
    dry_run: bool = False,
    harness: str | None = None,
) -> CompareResult:
    pack = pack.expanduser().resolve()
    compare_id = compare_id or uuid.uuid4().hex[:12]
    preflight_versions_compare(pack, run_ids=run_ids, git_refs=git_refs, dry_run=dry_run)
    if dry_run:
        return CompareResult(
            exit_code=0,
            payload=_versions_dry_run_payload(
                pack, compare_id=compare_id, run_ids=run_ids, git_refs=git_refs
            ),
        )
    try:
        return _run_versions_compare(
            pack,
            run_ids=run_ids,
            git_refs=git_refs,
            root=root,
            rerun=rerun,
            compare_id=compare_id,
            run_check_fn=run_check_fn,
            harness=harness,
        )
    except CompareError as exc:
        _append_compare_failure(pack, compare_id=compare_id, mode="versions", exc=exc)
        raise


def _rerun_arms(pack: Path, run_ids: list[str]) -> list[CompareArmSpec]:
    configs = []
    for rid in run_ids:
        for row in load_history(pack, limit=0):
            if row.get("run_id") == rid:
                cfg = row.get("config")
                if isinstance(cfg, dict):
                    configs.append(cfg)
                break
    if len(configs) != 2:
        raise CompareError("Could not load run configs for re-run.")
    arms: list[CompareArmSpec] = []
    for idx, (_rid, cfg) in enumerate(zip(run_ids, configs, strict=True)):
        arms.append(
            CompareArmSpec(
                arm_id=_arm_ids(2)[idx],
                label=str(cfg.get("label") or arm_label_defaults(2)[idx]),
                harness_pref=str(cfg.get("harness_pref") or cfg.get("harness") or "auto"),
                model=_blank(cfg.get("model")),
                timeout_sec=_as_int(cfg.get("timeout_sec")),
                temperature=_as_float(cfg.get("temperature")),
                reasoning_effort=_blank(cfg.get("reasoning_effort")),
            )
        )
    return arms


def _history_arm_rows(
    run_ids: list[str], reports: list[dict[str, Any]], case_ids: list[str]
) -> list[dict[str, Any]]:
    arm_rows: list[dict[str, Any]] = []
    for idx, (rid, report) in enumerate(zip(run_ids, reports, strict=True)):
        arm_id = _arm_ids(2)[idx]
        passed_count, task_count, tasks = _arm_stats_from_report(report, case_ids)
        arm_row: dict[str, Any] = {
            "arm_id": arm_id,
            "label": f"Run {rid[:6]}",
            "subtitle": str(report.get("harness") or ""),
            "source": "history",
            "run_id": rid,
            "passed": report.get("passed"),
            "passed_count": passed_count,
            "task_count": task_count,
            "usage": _usage_from_report(report),
            "duration_sec": None,
            "task_by_id": tasks,
        }
        sph = _skill_pack_hash_from_report(report)
        if sph:
            arm_row["skill_pack_hash"] = sph
        arm_rows.append(arm_row)
    return arm_rows


def _versions_payload(
    pack: Path,
    *,
    compare_id: str,
    fingerprint: str,
    case_ids: list[str],
    arm_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "kind": "compare",
        "compare_id": compare_id,
        "mode": "versions",
        "skill": pack.name,
        "pack_fingerprint": fingerprint,
        "pack_case_ids": case_ids,
        "status": "done",
        "arms": [{key: val for key, val in arm.items() if key != "task_by_id"} for arm in arm_rows],
        "cases": _build_cases(arm_rows, case_ids),
        "spend": {"cap_usd": None, "spent_usd": None, "stopped_reason": None},
        "error": None,
    }


def _run_versions_compare(
    pack: Path,
    *,
    run_ids: list[str] | None = None,
    git_refs: list[str] | None = None,
    root: Path,
    rerun: bool = False,
    compare_id: str,
    run_check_fn: Callable[..., Any] | None = None,
    harness: str | None = None,
) -> CompareResult:
    if git_refs and len(git_refs) == 2:
        from skillgate_ai.compare_git import run_git_versions_compare

        chosen = _normalize_compare_harness(harness) or harness_from_history(pack)
        return run_git_versions_compare(
            pack,
            refs=git_refs,
            compare_id=compare_id,
            root=root,
            run_check_fn=run_check_fn,
            harness=chosen,
        )
    if run_ids and len(run_ids) == 2 and run_ids[0] == run_ids[1]:
        raise CompareError(
            "Pick two different history runs.",
            hint="Use two distinct run ids from `skillgate history`.",
        )
    if not run_ids or len(run_ids) != 2:
        recent = [
            str(row.get("run_id") or "") for row in load_history(pack, limit=8) if row.get("run_id")
        ]
        hint = f"Recent runs: {', '.join(recent)}" if recent else "Use --run twice or --git twice."
        raise CompareError("Pick two history runs or two git refs.", hint=hint)
    if rerun:
        arms = _rerun_arms(pack, run_ids)
        return run_models_compare(
            pack,
            arms=arms,
            root=root,
            compare_id=compare_id,
            run_check_fn=run_check_fn,
        )

    reports = [_history_report(pack, rid) for rid in run_ids]
    fps = [str(r.get("pack_fingerprint") or "") for r in reports]
    if fps[0] != fps[1]:
        right = f"{fps[1][:12]}…" if fps[1] else "unknown"
        raise CompareError(
            "These runs used different Datasets.",
            hint=f"{fps[0][:12]}… vs {right}",
        )
    case_ids = _case_ids_from_report(reports[0])
    if not case_ids:
        case_ids = _case_ids_from_report(reports[1])
    arm_rows = _history_arm_rows(run_ids, reports, case_ids)
    payload = _versions_payload(
        pack, compare_id=compare_id, fingerprint=fps[0], case_ids=case_ids, arm_rows=arm_rows
    )
    append_compare(pack, row=payload)
    return CompareResult(exit_code=0, payload=payload)
