"""Human-readable reports for CLI and GitHub Actions."""

from __future__ import annotations

from typing import Any

from skillgate_ai.engine import EvalProgress, SuiteReport, TaskProgress, TaskReport
from skillgate_ai.eval_config import customer_run_details
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
    label = customer_run_details(report.config)
    if label:
        lines.append(f"config  {label}")
    cost = _cost_line(report)
    if cost:
        lines.append(cost)
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
            lines.append("Paste this description into SKILL.md:")
            lines.append(report.advice.paste.rstrip())
    return "\n".join(lines)


def _cost_line(report: SuiteReport) -> str:
    usage = report.usage_totals
    if not usage:
        return ""
    label = usage.get("agent_cost_label")
    if isinstance(label, str) and label.strip():
        return f"cost   {label.strip()}"
    amount = usage.get("cost_usd")
    if amount is not None:
        return f"cost   ${float(amount):.2f}"
    return ""


def format_github(report: SuiteReport) -> str:
    gate = "GREEN" if report.passed else "RED"
    emoji = "🟢" if report.passed else "🔴"
    lines = [
        f"## {emoji} Skill Gate · {gate}",
        "",
        f"**{report.title}** — skill `{report.skill}` · "
        f"{report.passed_count}/{len(report.tasks)} tasks passed",
    ]
    label = customer_run_details(report.config)
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
                if task.advice.target == "description" and task.advice.paste:
                    lines.append(
                        f"Change this in SKILL.md ({task.advice.target}): {task.advice.change}"
                    )
                    lines.append("")
                    lines.append("```")
                    lines.append(task.advice.paste.rstrip())
                    lines.append("```")
                elif task.advice.change:
                    lines.append(task.advice.change)
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
    payload = {
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
            passed=bool(task.passed),
            scores=list(task.scores),
            selected_skill=task.selected_skill,
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
    from skillgate_ai.judge_copy import (
        couldnt_score_line,
        customer_scorer_name,
        scored_by_phrase,
    )

    scored_stamp: dict | None = None
    failed_stamp: dict | None = None
    failed_reason: str | None = None
    saw_skip = False
    for task in report.tasks:
        judge = task.judge if isinstance(task.judge, dict) else None
        if not isinstance(judge, dict):
            continue
        provider = str(judge.get("provider") or "")
        status = str(judge.get("status") or "")
        if status == "completed" and _has_choice_answers(judge):
            scored_stamp = judge
        elif status == "error" and failed_stamp is None:
            failed_stamp = judge
            reasons = [
                str(item).strip() for item in (judge.get("reasons") or []) if str(item).strip()
            ]
            if reasons:
                failed_reason = reasons[0]
        if status == "skip" or provider == "skip":
            saw_skip = True
    if scored_stamp is not None:
        return scored_by_phrase(customer_scorer_name(scored_stamp))
    if failed_stamp is not None:
        return couldnt_score_line(failed_stamp, failed_reason)
    stamp = _judge_stamp(report)
    skip = (
        saw_skip
        or str(stamp.get("provider") or "") == "skip"
        or str(stamp.get("display_name") or "") == "Checks"
    )
    live = is_live_harness(report.harness)
    if skip:
        if live:
            return "The skill ran live. Quality was not scored."
        return "Quality was not scored."
    if stamp:
        return scored_by_phrase(customer_scorer_name(stamp))
    return ""


def _task_fail_line(task: TaskReport) -> str:
    judge = task.judge if isinstance(task.judge, dict) else {}
    if isinstance(judge, dict):
        from skillgate_ai.advice import behavior_fail_line, behavior_question_ids

        questions = behavior_question_ids(judge)
        if questions:
            return behavior_fail_line(questions[0])
        extras = judge.get("extra_failures")
        if isinstance(extras, list):
            for item in extras:
                text = str(item).strip()
                if text:
                    return text
    why = judge.get("why") if isinstance(judge, dict) else None
    if isinstance(why, str) and why.strip():
        return why.strip()
    return task.failures[0] if task.failures else "This check did not pass."


def _task_happened(task: TaskReport) -> str:
    """Plain What happened line. Never blank."""
    if task.passed:
        warnings = _task_warnings(task)
        if warnings:
            return warnings[0]
        if task.expect_skill is None:
            return "No skill was picked, as expected."
        return "Output matched what was expected."
    return _task_fail_line(task)


def _scoring_endpoint(report: SuiteReport) -> str | None:
    for task in report.tasks:
        judge = task.judge if isinstance(task.judge, dict) else None
        if not isinstance(judge, dict):
            continue
        endpoint = judge.get("scoring_endpoint")
        if isinstance(endpoint, str) and endpoint.strip():
            return endpoint.strip()
    return None


def _cell_answer(cell: dict, answer: Any = None) -> str:
    merged = dict(cell)
    if isinstance(answer, dict):
        for key in ("choice", "probability", "score"):
            if merged.get(key) in (None, "") and answer.get(key) is not None:
                merged[key] = answer[key]
    choice = str(merged.get("choice") or "").strip()
    if choice:
        return choice
    probability = merged.get("probability")
    if isinstance(probability, (int, float)) and not isinstance(probability, bool):
        return "Yes" if float(probability) >= 0.8 else "No"
    score = merged.get("score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        return str(score)
    if isinstance(score, str) and score.strip():
        return score.strip()
    reason = str(merged.get("reason") or "").strip()
    if reason.lower().startswith("not available"):
        return "Not available"
    label = str(merged.get("label") or "").strip()
    if label.lower() in {"path", "how it ran"}:
        return "Not available"
    return reason or "Not available"


def _task_check_answers(task: TaskReport) -> tuple[list[dict[str, str]], str]:
    """Plain expandable answers. OpenAI cells, else what the checks recorded."""
    judge = task.judge if isinstance(task.judge, dict) else {}
    raw = judge.get("cells") if isinstance(judge, dict) else None
    cells: list[dict] = []
    if isinstance(raw, dict):
        cells = [item for item in raw.values() if isinstance(item, dict)]
    elif isinstance(raw, list):
        cells = [item for item in raw if isinstance(item, dict)]
    if cells:
        answers_map = judge.get("answers") if isinstance(judge.get("answers"), dict) else {}
        rows: list[dict[str, str]] = []
        if isinstance(raw, dict):
            pairs = (
                (str(key), cell) for key, cell in raw.items() if isinstance(cell, dict)
            )
        else:
            pairs = ((str(cell.get("label") or ""), cell) for cell in cells)
        for key, cell in pairs:
            rows.append(
                {
                    "label": str(cell.get("label") or "").strip() or "Check",
                    "answer": _cell_answer(cell, answers_map.get(key)),
                }
            )
        return rows, "openai"
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
