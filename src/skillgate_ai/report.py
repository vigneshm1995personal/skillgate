"""Human-readable reports for CLI and GitHub Actions."""

from __future__ import annotations

from skillgate_ai.eval_config import config_label
from skillgate_ai.engine import EvalProgress, SuiteReport, TaskProgress, TaskReport
from skillgate_ai.metrics import suite_metrics_summary


def format_cli(report: SuiteReport) -> str:
    gate = "GREEN" if report.passed else "RED"
    lines = [
        f"Skill Gate  ·  {report.title}  ·  {gate}",
        f"skill `{report.skill}`  ·  {report.passed_count}/{len(report.tasks)} tasks passed",
    ]
    who = scored_by(report)
    if who:
        lines.append(_scored_by_line(who))
    label = config_label(report.config)
    if label:
        lines.append(f"config  {label}")
    lines.append("")
    for task in report.tasks:
        mark = "PASS" if task.passed else "FAIL"
        if task.passed:
            lines.append(f"  {mark}  {task.task_id}")
            for warning in _task_warnings(task):
                lines.append(f"       {warning}")
            continue
        why = _task_fail_line(task)
        lines.append(f"  {mark}  {task.task_id} — {why}")
        if task.advice:
            lines.append(f"       why:  {task.advice.why}")
            lines.append(f"       fix:  {task.advice.change}")
    lines.append("")
    if report.passed:
        lines.append("Gate is green.")
    else:
        failed = ", ".join(t.task_id for t in report.failed_tasks)
        lines.append(f"Gate is red. Failed tasks: {failed}")
        if report.advice and report.advice.paste:
            if report.advice.demo_note:
                lines.append(report.advice.demo_note)
            lines.append("Corrected SKILL.md description (not the current one):")
            lines.append(report.advice.paste.rstrip())
    return "\n".join(lines)


def format_github(report: SuiteReport) -> str:
    gate = "GREEN" if report.passed else "RED"
    emoji = "🟢" if report.passed else "🔴"
    lines = [
        f"## {emoji} Skill Gate · {gate}",
        "",
        f"**{report.title}** — skill `{report.skill}` · "
        f"{report.passed_count}/{len(report.tasks)} tasks passed",
    ]
    label = config_label(report.config)
    if label:
        lines += ["", f"Config: `{label}`"]
    who = scored_by(report)
    if who:
        lines += ["", _scored_by_line(who)]
    lines += [
        "",
        "| Task | Result | What happened |",
        "| --- | --- | --- |",
    ]
    for task in report.tasks:
        result = "pass" if task.passed else "FAIL"
        if task.passed:
            what = "; ".join(_task_warnings(task)) if _task_warnings(task) else "ok"
        else:
            what = _task_fail_line(task)
            extra = "; ".join(task.failures[1:]) if len(task.failures) > 1 else ""
            if extra:
                what = f"{what}; {extra}"
        lines.append(f"| `{task.task_id}` | **{result}** | {what} |")
    failed = report.failed_tasks
    if failed:
        lines += ["", "### Failed tasks — what to change", ""]
        for task in failed:
            lines.append(f"**{task.task_id}** — {_task_fail_line(task)}")
            if task.advice:
                lines.append("")
                lines.append(task.advice.why)
                lines.append("")
                lines.append(f"Change this in SKILL.md ({task.advice.target}): {task.advice.change}")
                lines.append("")
                lines.append("```")
                lines.append(task.advice.paste.rstrip())
                lines.append("```")
                lines.append("")
    else:
        lines += ["", "All tasks passed."]
    return "\n".join(lines) + "\n"


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
        "failed_task_ids": [task.task_id for task in done if not task.passed],
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
    return {
        "suite": report.suite,
        "title": report.title,
        "skill": report.skill,
        "skill_description": report.skill_description,
        "harness": report.harness,
        "sandbox": report.sandbox,
        "passed": report.passed,
        "gate": "green" if report.passed else "red",
        "passed_count": report.passed_count,
        "task_count": len(report.tasks),
        "failed_task_ids": [t.task_id for t in report.failed_tasks],
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
    }


def _progress_task_to_dict(task: TaskProgress) -> dict:
    if task.status != "done":
        out: dict = {
            "id": task.task_id,
            "prompt": task.prompt,
            "status": task.status,
            "passed": None,
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
            expect_skill=None,
            passed=bool(task.passed),
            scores=list(task.scores),
            selected_skill=None,
            failures=list(task.failures),
            transcript=task.transcript,
            judge=task.judge,
            spans=task.spans,
            metrics=task.metrics,
            usage=task.usage,
        )
    )
    payload["status"] = "done"
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


def _task_to_dict(task: TaskReport) -> dict:
    return {
        "id": task.task_id,
        "prompt": task.prompt,
        "passed": task.passed,
        "skipped": task.skipped,
        "expect_skill": task.expect_skill,
        "selected_skill": task.selected_skill,
        "failures": task.failures,
        "advice": _advice_to_dict(task.advice) if task.advice else None,
        "transcript": task.transcript,
        "spans": getattr(task, "spans", None),
        "files": list(task.files),
        "usage": task.usage,
        "judge": task.judge,
        "metrics": getattr(task, "metrics", None),
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


def scored_by(report: SuiteReport) -> str:
    cfg = report.config if isinstance(report.config, dict) else {}
    judge_cfg = cfg.get("judge") if isinstance(cfg, dict) else None
    if isinstance(judge_cfg, dict):
        name = judge_cfg.get("display_name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    for task in report.tasks:
        judge = task.judge if isinstance(task.judge, dict) else None
        if isinstance(judge, dict):
            name = judge.get("display_name")
            if isinstance(name, str) and name.strip():
                return name.strip()
    return ""


def _scored_by_line(who: str) -> str:
    if who == "Built-in checker":
        return "Built-in checker scored this run. This is not a live model."
    return f"{who} scored this run."


def _task_fail_line(task: TaskReport) -> str:
    judge = task.judge if isinstance(task.judge, dict) else {}
    why = judge.get("why") if isinstance(judge, dict) else None
    if isinstance(why, str) and why.strip():
        return why.strip()
    return task.failures[0] if task.failures else "failed"


def _task_warnings(task: TaskReport) -> list[str]:
    judge = task.judge if isinstance(task.judge, dict) else {}
    raw = judge.get("warnings") if isinstance(judge, dict) else None
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


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
