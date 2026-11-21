"""Compare runs: models (live arms) and versions (history / git)."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from skillgate_ai.compare.core import (
    DEFAULT_MAX_SPEND_USD,
    MIN_ARMS,
    CompareArmSpec,
    CompareError,
    CompareResult,
    _resolve_compare_case_ids,
    _resolved_arm_model,
    checks_for_case_ids,
    validate_compare_plan,
)
from skillgate_ai.compare.payload import (
    _build_cases,
    _dry_run_payload,
    _subtitle_for_arm,
    _task_map,
    _usage_for_task_ids,
)
from skillgate_ai.compare_control import (
    clear_compare_cancel,
    create_compare_control,
)
from skillgate_ai.gate import run_check
from skillgate_ai.history import append_compare
from skillgate_ai.live import create_control, drop_control


def _append_compare_failure(
    pack: Path,
    *,
    compare_id: str,
    mode: str,
    exc: CompareError,
) -> None:
    append_compare(
        pack,
        row={
            "kind": "compare",
            "compare_id": compare_id,
            "mode": mode,
            "skill": pack.name,
            "status": "error",
            "error": {"message": exc.message, "hint": exc.hint},
            "arms": [],
            "cases": [],
        },
    )


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
    compare_id = compare_id or uuid.uuid4().hex[:12]
    try:
        return _run_models_compare(
            pack,
            arms=arms,
            root=root,
            max_spend_usd=max_spend_usd,
            case_ids=case_ids,
            dry_run=dry_run,
            compare_id=compare_id,
            run_check_fn=run_check_fn,
        )
    except CompareError as exc:
        if not dry_run:
            _append_compare_failure(pack, compare_id=compare_id, mode="models", exc=exc)
        raise


def _run_arm(
    spec: CompareArmSpec,
    *,
    runner: Callable[..., Any],
    pack: Path,
    root: Path,
    run_checks: list[dict[str, Any]] | None,
    job_control: Any,
) -> tuple[str, Any, float]:
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
            checks=run_checks,
            **spec.to_run_kwargs(),
        )
    finally:
        drop_control(run_id)
        job_control.set_current_run(None)
    duration_sec = round(time.monotonic() - started, 3)
    if result.error or result.report is None:
        err = CompareError(
            result.error.get("message") if result.error else "Compare arm failed to run.",
            hint=result.error.get("hint") if result.error else None,
        )
        if result.exit_code == 2:
            err.exit_code = 2
        raise err
    return run_id, result, duration_sec


def _live_arm_row(
    spec: CompareArmSpec,
    report: dict[str, Any],
    *,
    run_id: str,
    duration_sec: float,
    active_case_ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    tasks = _task_map(report)
    tasks = {key: tasks[key] for key in active_case_ids if key in tasks}
    passed_count = sum(1 for task in tasks.values() if task.get("passed") is True)
    task_count = len(active_case_ids)
    usage = _usage_for_task_ids(report, active_case_ids)
    row = {
        "arm_id": spec.arm_id,
        "label": spec.label,
        "subtitle": _subtitle_for_arm(spec, report.get("harness")),
        "source": "live",
        "run_id": run_id,
        "passed": passed_count == task_count and task_count > 0,
        "passed_count": passed_count,
        "task_count": task_count,
        "usage": usage,
        "duration_sec": duration_sec,
        "model": _resolved_arm_model(report, spec.model),
        "requested_model": spec.model,
        "config": report.get("config"),
        "task_by_id": tasks,
    }
    return row, usage


def _models_payload(
    pack: Path,
    *,
    compare_id: str,
    pack_fp: str | None,
    pack_case_ids: list[str],
    status: str,
    arm_rows: list[dict[str, Any]],
    active_case_ids: list[str],
    max_spend_usd: float | None,
    spent: float,
    stopped_reason: str | None,
) -> dict[str, Any]:
    cases = _build_cases(arm_rows, active_case_ids)
    return {
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


def _run_models_compare(
    pack: Path,
    *,
    arms: list[CompareArmSpec],
    root: Path,
    max_spend_usd: float | None = DEFAULT_MAX_SPEND_USD,
    case_ids: list[str] | None = None,
    dry_run: bool = False,
    compare_id: str,
    run_check_fn: Callable[..., Any] | None = None,
) -> CompareResult:
    validate_compare_plan(arms, max_spend_usd=max_spend_usd)
    runner = run_check_fn or run_check
    resolved_case_ids = _resolve_compare_case_ids(pack, case_ids)
    if dry_run:
        return CompareResult(
            exit_code=0,
            payload=_dry_run_payload(
                pack,
                arms=arms,
                compare_id=compare_id,
                case_ids=resolved_case_ids,
                max_spend_usd=max_spend_usd,
            ),
        )

    arm_rows: list[dict[str, Any]] = []
    pack_fp: str | None = None
    pack_case_ids: list[str] = resolved_case_ids
    spent = 0.0
    run_checks = checks_for_case_ids(pack, resolved_case_ids) if case_ids else None
    active_case_ids = resolved_case_ids
    stopped_reason: str | None = None
    exit_code = 0
    job_control = create_compare_control(root, compare_id, skill=pack.name, mode="models")

    try:
        for spec in arms:
            if job_control.cancelled():
                stopped_reason = "cancelled"
                break
            if max_spend_usd is not None and spent >= max_spend_usd:
                stopped_reason = "spend_cap"
                break
            run_id, result, duration_sec = _run_arm(
                spec,
                runner=runner,
                pack=pack,
                root=root,
                run_checks=run_checks,
                job_control=job_control,
            )
            from skillgate_ai.report import report_to_dict

            report = report_to_dict(result.report)
            fp = str(report.get("pack_fingerprint") or "")
            if pack_fp is None:
                pack_fp = fp
            elif fp and fp != pack_fp:
                raise CompareError(
                    "Dataset fingerprint changed between arms.",
                    hint=f"First arm: {pack_fp[:12]}… · this arm: {fp[:12]}…",
                )
            row, usage = _live_arm_row(
                spec,
                report,
                run_id=run_id,
                duration_sec=duration_sec,
                active_case_ids=active_case_ids,
            )
            if usage and usage.get("cost_usd") is not None:
                spent += float(usage["cost_usd"])
            arm_rows.append(row)
            if max_spend_usd is not None and spent >= max_spend_usd:
                stopped_reason = "spend_cap"
                break
    finally:
        clear_compare_cancel(root, compare_id)

    if len(arm_rows) < MIN_ARMS and stopped_reason != "cancelled":
        raise CompareError(
            "Not enough arms finished to compare.",
            hint="Raise the spend cap or use fewer arms.",
        )

    status = "cancelled" if stopped_reason == "cancelled" else "done"
    payload = _models_payload(
        pack,
        compare_id=compare_id,
        pack_fp=pack_fp,
        pack_case_ids=pack_case_ids,
        status=status,
        arm_rows=arm_rows,
        active_case_ids=active_case_ids,
        max_spend_usd=max_spend_usd,
        spent=spent,
        stopped_reason=stopped_reason,
    )
    append_compare(pack, row=payload)
    return CompareResult(exit_code=exit_code, payload=payload)
