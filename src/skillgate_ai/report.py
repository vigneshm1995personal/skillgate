"""Human-readable reports for CLI and GitHub Actions."""

from __future__ import annotations

from skillgate_ai.eval_config import config_label
from skillgate_ai.engine import EvalProgress, SuiteReport, TaskProgress, TaskReport
from skillgate_ai.harness import is_live_harness
from skillgate_ai.metrics import suite_metrics_summary


def format_cli(report: SuiteReport) -> str:
    gate = "GREEN" if report.passed else "RED"
    lines = [
        f"Skill Gate  ·  {report.title}  ·  {gate}",
        f"skill `{report.skill}`  ·  {report.passed_count}/{len(report.tasks)} tasks passed",
    ]
    who = scored_by_line(report)
    if who:
        lines.append(who)
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
    who = scored_by_line(report)
    if who:
        lines += ["", who]
    lines += [
        "",
        "| Task | Result | What happened |",
        "| --- | --- | --- |",
    ]
    for task in report.tasks:
        result = "pass" if task.passed else "FAIL"
        if task.passed:
            what = _task_happened(task)
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
        "scored_by": scored_by_line(report),
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
    answers, kind = _task_check_answers(task)
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


def _judge_stamp(report: SuiteReport) -> dict:
    cfg = report.config if isinstance(report.config, dict) else {}
    judge = cfg.get("judge") if isinstance(cfg, dict) else None
    return judge if isinstance(judge, dict) else {}


def _has_choice_answers(judge: dict) -> bool:
    answers = judge.get("answers")
    if not isinstance(answers, dict) or not answers:
        return False
    for item in answers.values():
        if isinstance(item, str) and item.strip():
            return True
        if isinstance(item, dict) and str(item.get("choice") or "").strip():
            return True
    return False


def scored_by_line(report: SuiteReport) -> str:
    """Who scored, from actual answers — not the pre-run stamp."""
    openai_scored = False
    openai_reason: str | None = None
    openai_failed = False
    saw_skip = False
    for task in report.tasks:
        judge = task.judge if isinstance(task.judge, dict) else None
        if not isinstance(judge, dict):
            continue
        provider = str(judge.get("provider") or "")
        status = str(judge.get("status") or "")
        if provider == "openai" or str(judge.get("display_name") or "") == "OpenAI (your key)":
            if status == "completed" and _has_choice_answers(judge):
                openai_scored = True
            elif status == "error":
                openai_failed = True
                reasons = [
                    str(item).strip() for item in (judge.get("reasons") or []) if str(item).strip()
                ]
                if reasons and openai_reason is None:
                    openai_reason = reasons[0]
        if status == "skip" or provider == "skip":
            saw_skip = True
    if openai_scored:
        return "OpenAI (your key) scored this run."
    if openai_failed:
        extra = openai_reason or "OpenAI scoring failed."
        return f"OpenAI couldn't score this run. {extra}"
    stamp = _judge_stamp(report)
    skip = (
        saw_skip
        or str(stamp.get("provider") or "") == "skip"
        or str(stamp.get("display_name") or "") == "Built-in checker"
    )
    live = is_live_harness(report.harness)
    if skip:
        if live:
            return "The skill ran live. The built-in checker scored it."
        return "Built-in checker scored this run. This is not a live model."
    name = str(stamp.get("display_name") or "").strip()
    if name:
        return f"{name} scored this run."
    return ""


def _task_fail_line(task: TaskReport) -> str:
    judge = task.judge if isinstance(task.judge, dict) else {}
    why = judge.get("why") if isinstance(judge, dict) else None
    if isinstance(why, str) and why.strip():
        return why.strip()
    return task.failures[0] if task.failures else "This check did not pass."


def _task_happened(task: TaskReport) -> str:
    """Plain What happened line. Never blank."""
    if task.passed:
        warnings = _task_warnings(task)
        return warnings[0] if warnings else "Output matched what was expected."
    return _task_fail_line(task)


def _cell_answer(cell: dict) -> str:
    choice = str(cell.get("choice") or "").strip()
    if choice:
        return choice
    reason = str(cell.get("reason") or "").strip()
    if reason.lower().startswith("not available"):
        return "Not available"
    label = str(cell.get("label") or "").strip()
    if label.lower() == "path":
        return "Not available"
    return reason or "Not available"


def _task_check_answers(task: TaskReport) -> tuple[list[dict[str, str]], str]:
    """Plain expandable answers. OpenAI cells, else what the built-in checker checked."""
    judge = task.judge if isinstance(task.judge, dict) else {}
    raw = judge.get("cells") if isinstance(judge, dict) else None
    cells: list[dict] = []
    if isinstance(raw, dict):
        cells = [item for item in raw.values() if isinstance(item, dict)]
    elif isinstance(raw, list):
        cells = [item for item in raw if isinstance(item, dict)]
    if cells:
        return (
            [
                {
                    "label": str(cell.get("label") or "").strip() or "Check",
                    "answer": _cell_answer(cell),
                }
                for cell in cells
            ],
            "openai",
        )
    rows: list[dict[str, str]] = []
    for score in task.scores:
        title = (score.headline or score.detail or "Check").strip()
        mark = "Yes" if score.passed else "No"
        extra = ""
        if score.detail and score.detail != title:
            extra = f" — {score.detail}"
        rows.append({"label": title, "answer": f"{mark}{extra}"})
    return rows, "builtin"


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
