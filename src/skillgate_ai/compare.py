"""Compare runs: models (live arms) and versions (history / git)."""

from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from skillgate_ai.errors import SkillGateError
from skillgate_ai.eval_config import harness_display_name
from skillgate_ai.gate import run_check
from skillgate_ai.compare_control import clear_compare_cancel, create_compare_control
from skillgate_ai.history import append_compare, load_compares, load_history
from skillgate_ai.live import create_control, drop_control

MAX_ARMS = 4
MIN_ARMS = 2
DEFAULT_MAX_SPEND_USD = 5.0


class CompareError(SkillGateError):
    exit_code = 1


@dataclass(frozen=True)
class CompareArmSpec:
    arm_id: str
    label: str
    harness_pref: str
    model: str | None = None
    timeout_sec: int | None = None
    temperature: float | None = None
    reasoning_effort: str | None = None

    def to_run_kwargs(self) -> dict[str, Any]:
        return {
            "harness": self.harness_pref,
            "model": self.model,
            "timeout": self.timeout_sec,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
        }


@dataclass
class CompareResult:
    exit_code: int
    payload: dict[str, Any]


def arm_label_defaults(count: int) -> list[str]:
    letters = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    return [f"Arm {letters[i]}" for i in range(count)]


def parse_arm_spec(raw: str, *, arm_id: str, index: int) -> CompareArmSpec:
    text = (raw or "").strip()
    if not text:
        raise CompareError("Each arm needs a label and harness.", hint="Use --arm 'Label:codex'.")
    parts = text.split(":")
    label = parts[0].strip() or arm_label_defaults(index + 1)[index]
    harness = (parts[1] if len(parts) > 1 else "auto").strip() or "auto"
    model = parts[2].strip() if len(parts) > 2 and parts[2].strip() else None
    return CompareArmSpec(arm_id=arm_id, label=label, harness_pref=harness, model=model or None)


def parse_arm_file(path: Path, *, arm_id: str, index: int) -> CompareArmSpec:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CompareError(f"Arm file must be a JSON object: {path}")
    label = str(data.get("label") or arm_label_defaults(index + 1)[index]).strip()
    harness = str(data.get("harness_pref") or data.get("harness") or "auto").strip()
    return CompareArmSpec(
        arm_id=arm_id,
        label=label,
        harness_pref=harness,
        model=_blank(data.get("model")),
        timeout_sec=_as_int(data.get("timeout_sec")),
        temperature=_as_float(data.get("temperature")),
        reasoning_effort=_blank(data.get("reasoning_effort")),
    )


def _blank(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _as_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _arm_ids(n: int) -> list[str]:
    return [chr(ord("a") + i) for i in range(n)]


def arm_id_for_index(index: int) -> str:
    if index < 0 or index >= MAX_ARMS:
        raise CompareError(f"Compare supports at most {MAX_ARMS} arms.")
    return chr(ord("a") + index)


def _usage_from_report(report: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(report, dict):
        return None
    usage = report.get("usage")
    return usage if isinstance(usage, dict) else None


def _task_map(report: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(report, dict):
        return {}
    tasks = report.get("tasks")
    if not isinstance(tasks, list):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for task in tasks:
        if isinstance(task, dict) and task.get("id"):
            out[str(task["id"])] = task
    return out


def _build_cases(arms: list[dict[str, Any]], case_ids: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for case_id in case_ids:
        results: dict[str, Any] = {}
        passes: list[bool] = []
        for arm in arms:
            arm_id = str(arm.get("arm_id") or "")
            task = (arm.get("task_by_id") or {}).get(case_id) or {}
            passed = task.get("passed")
            cell: dict[str, Any] = {"passed": passed}
            usage = task.get("usage")
            if isinstance(usage, dict):
                cell["usage"] = {
                    key: usage.get(key)
                    for key in ("tokens_total", "cost_usd")
                    if usage.get(key) is not None
                }
            if task.get("duration_sec") is not None:
                cell["duration_sec"] = task.get("duration_sec")
            results[arm_id] = cell
            if isinstance(passed, bool):
                passes.append(passed)
        disagreement = len(set(passes)) > 1 if passes else False
        rows.append({"case_id": case_id, "results": results, "disagreement": disagreement})
    return rows


def scrub_compare_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Customer-facing compare JSON (API / CLI --json)."""
    data = copy.deepcopy(payload)
    for arm in data.get("arms") or []:
        if not isinstance(arm, dict):
            continue
        cfg = arm.get("config")
        if isinstance(cfg, dict):
            cfg.pop("model", None)
            cfg.pop("config_label_raw", None)
            cfg.pop("judge", None)
            cfg.pop("judge_backend", None)
            cfg.pop("judge_model", None)
        arm.pop("task_by_id", None)
        for key in ("provider", "backend", "via_gateway"):
            arm.pop(key, None)
    return data


def _subtitle_for_arm(spec: CompareArmSpec, harness: str | None) -> str:
    return harness_display_name(harness or spec.harness_pref, spec.harness_pref)


def run_models_compare(
    pack: Path,
    *,
    arms: list[CompareArmSpec],
    root: Path,
    max_spend_usd: float | None = DEFAULT_MAX_SPEND_USD,
    case_ids: list[str] | None = None,
    dry_run: bool = False,
    compare_id: str | None = None,
    run_check_fn: Callable[..., Any] | None = None,
) -> CompareResult:
    pack = pack.expanduser().resolve()
    if len(arms) < MIN_ARMS or len(arms) > MAX_ARMS:
        raise CompareError(f"Compare needs {MIN_ARMS}–{MAX_ARMS} arms.")
    runner = run_check_fn or run_check
    compare_id = compare_id or uuid.uuid4().hex[:12]
    if dry_run:
        return CompareResult(
            exit_code=0,
            payload={
                "compare_id": compare_id,
                "mode": "models",
                "status": "dry_run",
                "arm_count": len(arms),
                "case_filter": case_ids,
            },
        )

    arm_rows: list[dict[str, Any]] = []
    pack_fp: str | None = None
    pack_case_ids: list[str] = []
    spent = 0.0
    stopped_reason: str | None = None
    exit_code = 0
    job_control = create_compare_control(root, compare_id)

    try:
        for spec in arms:
            if job_control.cancelled():
                stopped_reason = "cancelled"
                break
            if max_spend_usd is not None and spent >= max_spend_usd:
                stopped_reason = "spend_cap"
                break
            run_id = uuid.uuid4().hex[:12]
            job_control.set_current_run(run_id)
            run_control = create_control(run_id)
            started = time.monotonic()
            try:
                result = runner(
                    pack,
                    run_id=run_id,
                    source="compare",
                    root=root,
                    control=run_control,
                    **spec.to_run_kwargs(),
                )
            finally:
                drop_control(run_id)
                job_control.set_current_run(None)
            duration_sec = round(time.monotonic() - started, 3)
            if result.error or result.report is None:
                exit_code = 1
                err = CompareError(
                    result.error.get("message") if result.error else "Compare arm failed to run.",
                    hint=result.error.get("hint") if result.error else None,
                )
                if result.exit_code == 2:
                    err.exit_code = 2
                raise err
            from skillgate_ai.report import report_to_dict

            report = report_to_dict(result.report)
            fp = str(report.get("pack_fingerprint") or "")
            if pack_fp is None:
                pack_fp = fp
                pack_case_ids = list(report.get("pack_case_ids") or [])
            elif fp and fp != pack_fp:
                raise CompareError(
                    "Dataset fingerprint changed between arms.",
                    hint=f"First arm: {pack_fp[:12]}… · this arm: {fp[:12]}…",
                )
            tasks = _task_map(report)
            if case_ids:
                tasks = {key: tasks[key] for key in case_ids if key in tasks}
            usage = _usage_from_report(report)
            if usage and usage.get("cost_usd") is not None:
                spent += float(usage["cost_usd"])
            arm_rows.append(
                {
                    "arm_id": spec.arm_id,
                    "label": spec.label,
                    "subtitle": _subtitle_for_arm(spec, report.get("harness")),
                    "source": "live",
                    "run_id": run_id,
                    "passed": report.get("passed"),
                    "passed_count": report.get("passed_count"),
                    "task_count": report.get("task_count"),
                    "usage": usage,
                    "duration_sec": duration_sec,
                    "config": report.get("config"),
                    "task_by_id": tasks,
                }
            )
            if max_spend_usd is not None and spent >= max_spend_usd:
                stopped_reason = "spend_cap"
                break
    finally:
        clear_compare_cancel(root, compare_id)

    if len(arm_rows) < MIN_ARMS:
        if stopped_reason == "cancelled":
            pass
        else:
            raise CompareError(
                "Not enough arms finished to compare.",
                hint="Raise the spend cap or use fewer arms.",
            )

    status = "cancelled" if stopped_reason == "cancelled" else "done"
    cases = _build_cases(arm_rows, pack_case_ids if not case_ids else case_ids)
    payload: dict[str, Any] = {
        "kind": "compare",
        "compare_id": compare_id,
        "mode": "models",
        "skill": pack.name,
        "pack_fingerprint": pack_fp,
        "pack_case_ids": pack_case_ids,
        "status": status,
        "arms": [{key: val for key, val in arm.items() if key != "task_by_id"} for arm in arm_rows],
        "cases": cases,
        "spend": {
            "cap_usd": max_spend_usd,
            "spent_usd": spent,
            "stopped_reason": stopped_reason,
        },
        "error": None,
    }
    append_compare(pack, row=payload)
    return CompareResult(exit_code=exit_code, payload=payload)


def _history_report(pack: Path, run_id: str) -> dict[str, Any]:
    for row in load_history(pack, limit=0):
        if row.get("run_id") == run_id:
            report = row.get("report")
            if isinstance(report, dict):
                return report
            raise CompareError(f"Run {run_id} has no report.")
    raise CompareError(f"Unknown run {run_id}.")


def run_versions_compare(
    pack: Path,
    *,
    run_ids: list[str] | None = None,
    git_refs: list[str] | None = None,
    root: Path,
    rerun: bool = False,
    run_check_fn: Callable[..., Any] | None = None,
) -> CompareResult:
    pack = pack.expanduser().resolve()
    compare_id = uuid.uuid4().hex[:12]
    if git_refs and len(git_refs) == 2:
        from skillgate_ai.compare_git import run_git_versions_compare

        return run_git_versions_compare(
            pack,
            refs=git_refs,
            compare_id=compare_id,
            root=root,
            run_check_fn=run_check_fn,
        )
    if not run_ids or len(run_ids) != 2:
        raise CompareError("Pick two history runs or two git refs.")
    if rerun:
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
        arms = []
        for idx, (rid, cfg) in enumerate(zip(run_ids, configs, strict=True)):
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
        return run_models_compare(pack, arms=arms, root=root, run_check_fn=run_check_fn)

    reports = [_history_report(pack, rid) for rid in run_ids]
    fps = [str(r.get("pack_fingerprint") or "") for r in reports]
    if fps[0] != fps[1]:
        raise CompareError(
            "These runs used different Datasets.",
            hint=f"{fps[0][:12]}… vs {fps[1][:12]}…",
        )
    case_ids = list(reports[0].get("pack_case_ids") or [])
    arm_rows: list[dict[str, Any]] = []
    for idx, (rid, report) in enumerate(zip(run_ids, reports, strict=True)):
        arm_id = _arm_ids(2)[idx]
        tasks = _task_map(report)
        arm_row: dict[str, Any] = {
            "arm_id": arm_id,
            "label": f"Run {rid[:6]}",
            "subtitle": str(report.get("harness") or ""),
            "source": "history",
            "run_id": rid,
            "passed": report.get("passed"),
            "passed_count": report.get("passed_count"),
            "task_count": report.get("task_count"),
            "usage": _usage_from_report(report),
            "duration_sec": None,
            "task_by_id": tasks,
        }
        sph = report.get("skill_pack_hash")
        if isinstance(sph, str) and sph:
            arm_row["skill_pack_hash"] = sph
        arm_rows.append(arm_row)
    payload: dict[str, Any] = {
        "kind": "compare",
        "compare_id": compare_id,
        "mode": "versions",
        "skill": pack.name,
        "pack_fingerprint": fps[0],
        "pack_case_ids": case_ids,
        "status": "done",
        "arms": [{key: val for key, val in arm.items() if key != "task_by_id"} for arm in arm_rows],
        "cases": _build_cases(arm_rows, case_ids),
        "spend": {"cap_usd": None, "spent_usd": None, "stopped_reason": None},
        "error": None,
    }
    append_compare(pack, row=payload)
    return CompareResult(exit_code=0, payload=payload)


def find_compare(pack: Path, compare_id: str) -> dict[str, Any] | None:
    for row in load_compares(pack, limit=0):
        if row.get("compare_id") == compare_id:
            return row
    return None


def find_compare_anywhere(root: Path, compare_id: str) -> tuple[Path, dict[str, Any]] | None:
    from skillgate_ai.catalog import catalog_entries

    for entry in catalog_entries(root):
        path = Path(entry["absolute"])
        row = find_compare(path, compare_id)
        if row:
            return path, row
    return None


def list_compares(pack: Path, *, limit: int = 20) -> list[dict[str, Any]]:
    return load_compares(pack, limit=limit)
