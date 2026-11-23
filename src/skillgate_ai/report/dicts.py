"""Human-readable reports for CLI and GitHub Actions."""

from __future__ import annotations

from skillgate_ai.engine import EvalProgress, SuiteReport, TaskProgress, TaskReport
from skillgate_ai.metrics import suite_metrics_summary
from skillgate_ai.report.lines import _task_check_answers, _task_happened
from skillgate_ai.report.scoring import _report_gate, _scoring_endpoint, scored_by_line


def progress_to_dict(progress: EvalProgress) -> dict:
    done = [task for task in progress.tasks if task.status == "done"]
    return {
        "suite": progress.suite,
        "title": progress.title,
        "skill": progress.skill,
        "harness": progress.harness,
        "passed": None,
        "gate": None,
        "passed_count": sum(1 for task in done if task.passed),
        "task_count": progress.task_count,
        "completed_count": progress.completed_count,
        "current_task_id": progress.current_task_id,
        "failed_task_ids": [task.task_id for task in done if task.passed is False],
        "tasks": [_progress_task_to_dict(task) for task in progress.tasks],
        "advice": None,
        "config": progress.config,
        "pack_fingerprint": progress.pack_fingerprint,
        "pack_case_ids": list(progress.pack_case_ids or ()),
    }


def report_to_dict(report: SuiteReport) -> dict:
    primary = _advice_to_dict(report.advice) if report.advice else None
    if primary is None:
        for task in report.failed_tasks:
            if task.advice:
                primary = _advice_to_dict(task.advice)
                break
    tasks = [_task_to_dict(t) for t in report.tasks]
    payload = {
        "suite": report.suite,
        "title": report.title,
        "skill": report.skill,
        "skill_description": report.skill_description,
        "harness": report.harness,
        "sandbox": report.sandbox,
        "passed": report.passed,
        "gate": _report_gate(report),
        "passed_count": report.passed_count,
        "task_count": len(report.tasks),
        "failed_task_ids": [t.task_id for t in report.failed_tasks],
        "review_task_ids": [t.task_id for t in report.tasks if getattr(t, "review", False)],
        "tasks": tasks,
        "advice": primary,
        "note": report.note,
        "skill_path": report.skill_path,
        "demo_note": (primary or {}).get("demo_note"),
        "config": report.config,
        "timeout_effective": report.timeout_effective,
        "usage": report.usage_totals,
        "metrics": suite_metrics_summary(tasks),
        "pack_fingerprint": report.pack_fingerprint,
        "pack_case_ids": list(report.pack_case_ids or ()),
        "scored_by": scored_by_line(report),
    }
    endpoint = _scoring_endpoint(report)
    if endpoint:
        payload["scoring_endpoint"] = endpoint
    return payload


def _progress_task_to_dict(task: TaskProgress) -> dict:
    if task.status != "done":
        out: dict = {
            "id": task.task_id,
            "prompt": task.prompt,
            "status": task.status,
            "passed": None,
            "expect_skill": task.expect_skill,
        }
        # Mid-check live flush (Sandbox JSONL polls) may already have spans.
        if task.transcript:
            out["transcript"] = task.transcript
        if task.spans:
            out["spans"] = task.spans
        return out
    # TaskProgress carries spans (and transcript/judge/scores/usage) from engine._eval_progress.
    payload = _task_to_dict(
        TaskReport(
            task_id=task.task_id,
            prompt=task.prompt,
            expect_skill=task.expect_skill,
            passed=task.passed,
            scores=list(task.scores),
            selected_skill=task.selected_skill,
            review=bool(getattr(task, "review", False)),
            failures=list(task.failures),
            transcript=task.transcript,
            judge=task.judge,
            spans=task.spans,
            metrics=task.metrics,
            usage=task.usage,
        )
    )
    payload["status"] = task.status
    payload["review"] = bool(getattr(task, "review", False))
    payload["skipped"] = bool(task.skipped)
    payload.pop("advice", None)
    return payload


def hydrate_report_spans(payload: dict) -> dict:
    """Fill missing tasks[].spans from transcript JSONL (older mid-suite rows).

    Mutates ``payload`` in place and returns it. No-op when spans already present
    or transcript has no reconstructible JSONL events.
    """
    from skillgate_ai.spans import spans_from_jsonl

    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        return payload
    for task in tasks:
        if not isinstance(task, dict):
            continue
        if task.get("spans"):
            continue
        transcript = task.get("transcript") or ""
        if not str(transcript).strip():
            continue
        rebuilt = spans_from_jsonl(str(transcript))
        if rebuilt:
            task["spans"] = rebuilt
    return payload


def _task_status(task: TaskReport) -> str:
    if task.passed is None:
        return "not scored"
    if task.passed is False:
        return "fail"
    if getattr(task, "review", False):
        return "unsure"
    return "pass"


def _task_to_dict(task: TaskReport) -> dict:
    answers, kind = _task_check_answers(task)
    return {
        "id": task.task_id,
        "prompt": task.prompt,
        "passed": task.passed,
        "review": bool(getattr(task, "review", False)),
        "status": _task_status(task),
        "skipped": task.skipped,
        "expect_skill": task.expect_skill,
        "selected_skill": task.selected_skill,
        "failures": task.failures,
        "advice": _advice_to_dict(task.advice) if task.advice else None,
        "transcript": task.transcript,
        "spans": getattr(task, "spans", None),
        "files": list(task.files),
        "outputs": list(getattr(task, "outputs", None) or []),
        "usage": task.usage,
        "judge": task.judge,
        "metrics": getattr(task, "metrics", None),
        "model": getattr(task, "model", None),
        "happened": _task_happened(task),
        "check_kind": kind,
        "check_answers": answers,
        "scores": [
            {
                "scorer": s.scorer,
                "passed": s.passed,
                "headline": s.headline or s.detail,
                "detail": s.detail,
                "expected": s.expected,
                "actual": s.actual,
            }
            for s in task.scores
        ],
    }


def _advice_to_dict(advice) -> dict:
    return {
        "headline": advice.headline,
        "why": advice.why,
        "change": advice.change,
        "paste": advice.paste,
        "target": advice.target,
        "description": advice.description,
        "demo_note": advice.demo_note,
        "apply_label": advice.apply_label,
        "restore_scripts_from": advice.restore_scripts_from,
    }
