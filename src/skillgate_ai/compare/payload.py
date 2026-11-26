"""Compare runs: models (live arms) and versions (history / git)."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, NotRequired, TypedDict

from skillgate_ai.compare.core import CompareArmSpec, _blank
from skillgate_ai.eval_config import harness_display_name
from skillgate_ai.pack import skill_pack_hash


class CompareCell(TypedDict):
    passed: bool | None
    usage: NotRequired[dict[str, int | float]]
    duration_sec: NotRequired[float]


class CompareCaseRow(TypedDict):
    case_id: str
    results: dict[str, CompareCell]
    disagreement: bool


class ComparePlanArm(TypedDict):
    arm_id: str
    label: str
    subtitle: str
    source: str
    passed_count: int | None
    task_count: int
    usage: Mapping[str, Any] | None
    duration_sec: float | None


def _usage_for_task_ids(report: Mapping[str, Any], task_ids: list[str]) -> Mapping[str, Any] | None:
    tasks = _task_map(report)
    tokens = 0
    cost = 0.0
    found = False
    for task_id in task_ids:
        task = tasks.get(task_id) or {}
        raw_usage = task.get("usage")
        usage: Mapping[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        if usage.get("tokens_total") is not None:
            tokens += int(usage["tokens_total"])
            found = True
        if usage.get("cost_usd") is not None:
            cost += float(usage["cost_usd"])
            found = True
    if not found:
        return _usage_from_report(report)
    out: dict[str, int | float] = {}
    if tokens:
        out["tokens_total"] = tokens
    if cost:
        out["cost_usd"] = round(cost, 6)
    return out or None


def _dry_run_payload(
    pack: Path,
    *,
    arms: list[CompareArmSpec],
    compare_id: str,
    case_ids: list[str],
    max_spend_usd: float | None,
) -> dict[str, Any]:
    arm_rows: list[ComparePlanArm] = [
        {
            "arm_id": spec.arm_id,
            "label": spec.label,
            "subtitle": _plan_subtitle(spec),
            "source": "plan",
            "passed_count": None,
            "task_count": len(case_ids),
            "usage": None,
            "duration_sec": None,
        }
        for spec in arms
    ]
    cases: list[CompareCaseRow] = [
        {
            "case_id": cid,
            "results": {spec.arm_id: {"passed": None} for spec in arms},
            "disagreement": False,
        }
        for cid in case_ids
    ]
    return {
        "kind": "compare",
        "compare_id": compare_id,
        "mode": "models",
        "skill": pack.name,
        "pack_fingerprint": None,
        "pack_case_ids": case_ids,
        "status": "dry_run",
        "arms": arm_rows,
        "cases": cases,
        "spend": {
            "cap_usd": max_spend_usd,
            "spent_usd": None,
            "stopped_reason": None,
        },
        "error": None,
    }


def _skill_pack_hash_from_report(report: Mapping[str, Any]) -> str | None:
    stored = report.get("skill_pack_hash")
    if isinstance(stored, str) and stored:
        return stored
    skill_path = report.get("skill_path")
    if isinstance(skill_path, str) and skill_path:
        path = Path(skill_path)
        if path.is_dir():
            return skill_pack_hash(path)
    return None


def _usage_from_report(report: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if not isinstance(report, dict):
        return None
    usage = report.get("usage")
    return usage if isinstance(usage, dict) else None


def _task_map(report: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(report, dict):
        return {}
    tasks = report.get("tasks")
    if not isinstance(tasks, list):
        return {}
    out: dict[str, Mapping[str, Any]] = {}
    for task in tasks:
        if isinstance(task, dict) and task.get("id"):
            out[str(task["id"])] = task
    return out


def _build_cases(arms: Sequence[Mapping[str, Any]], case_ids: list[str]) -> list[CompareCaseRow]:
    rows: list[CompareCaseRow] = []
    for case_id in case_ids:
        results: dict[str, CompareCell] = {}
        passes: list[bool] = []
        for arm in arms:
            arm_id = str(arm.get("arm_id") or "")
            task = (arm.get("task_by_id") or {}).get(case_id) or {}
            passed = task.get("passed")
            cell: CompareCell = {"passed": passed}
            usage = task.get("usage")
            if isinstance(usage, dict):
                usage_row: dict[str, int | float] = {}
                for key in ("tokens_total", "cost_usd"):
                    raw = usage.get(key)
                    if raw is None:
                        continue
                    if key == "tokens_total":
                        usage_row[key] = int(raw)
                    else:
                        usage_row[key] = float(raw)
                if usage_row:
                    cell["usage"] = usage_row
            duration = task.get("duration_sec")
            if isinstance(duration, (int, float)) and not isinstance(duration, bool):
                cell["duration_sec"] = float(duration)
            results[arm_id] = cell
            if isinstance(passed, bool):
                passes.append(passed)
        disagreement = len(set(passes)) > 1 if passes else False
        rows.append({"case_id": case_id, "results": results, "disagreement": disagreement})
    return rows


def scrub_compare_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Strip compare-specific secrets (model/judge on arms) before customer JSON."""
    data = copy.deepcopy(payload)
    for arm in data.get("arms") or []:
        if not isinstance(arm, dict):
            continue
        cfg = arm.get("config")
        if isinstance(cfg, dict):
            if arm.get("model") is None:
                harness = str(cfg.get("harness") or "").strip().lower()
                if harness in {"cursor-agent", "codex", "claude", "claude-code"}:
                    arm["model"] = _blank(cfg.get("model"))
            cfg.pop("model", None)
            cfg.pop("config_label_raw", None)
            cfg.pop("judge", None)
            cfg.pop("judge_backend", None)
            cfg.pop("judge_model", None)
        arm.pop("task_by_id", None)
        for key in ("provider", "backend", "via_gateway"):
            arm.pop(key, None)
    return data


def scrub_customer_compare_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Compare JSON for CLI --json and browser/API (compare scrub + global browser scrub)."""
    from skillgate_ai.eval_config import customer_config_label
    from skillgate_ai.scrub import scrub_browser_payload

    data = scrub_browser_payload(scrub_compare_payload(payload))
    for arm in data.get("arms") or []:
        if not isinstance(arm, dict):
            continue
        raw_cfg = arm.get("config")
        cfg: dict[str, Any] = raw_cfg if isinstance(raw_cfg, dict) else {}
        harness = str(cfg.get("harness") or cfg.get("harness_pref") or "cursor-agent")
        arm["subtitle"] = harness_display_name(harness, harness)
        # Keep user arm labels from compare specs; only fill when missing.
        if not str(arm.get("label") or "").strip():
            arm["label"] = (
                customer_config_label(cfg, harness)
                if cfg
                else harness_display_name(harness, harness)
            )
    return data


def _subtitle_for_arm(spec: CompareArmSpec, harness: str | None) -> str:
    base = harness_display_name(harness or spec.harness_pref, spec.harness_pref)
    if spec.model:
        return f"{base} · {spec.model}"
    return base


def _plan_subtitle(spec: CompareArmSpec) -> str:
    return _subtitle_for_arm(spec, spec.harness_pref)


def _case_ids_from_report(report: Mapping[str, Any]) -> list[str]:
    tasks = report.get("tasks")
    if isinstance(tasks, list):
        ids = [str(item.get("id")) for item in tasks if isinstance(item, dict) and item.get("id")]
        if ids:
            return ids
    return list(report.get("pack_case_ids") or [])


def _arm_stats_from_report(
    report: Mapping[str, Any], case_ids: list[str]
) -> tuple[int, int, dict[str, Mapping[str, Any]]]:
    tasks = _task_map(report)
    active = case_ids or _case_ids_from_report(report)
    subset = {key: tasks[key] for key in active if key in tasks}
    passed_count = sum(1 for task in subset.values() if task.get("passed") is True)
    task_count = len(active) if active else len(subset)
    return passed_count, task_count, subset
