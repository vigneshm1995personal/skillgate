"""Human-readable reports for CLI and GitHub Actions."""

from __future__ import annotations

from skillgate_ai.engine import SuiteReport
from skillgate_ai.eval_config import customer_run_details
from skillgate_ai.judge_bank import UNSURE_REVIEW
from skillgate_ai.report.lines import (
    _extra_source_lines,
    _task_fail_line,
    _task_happened,
    _task_warnings,
)
from skillgate_ai.report.scoring import _report_gate, scored_by_line


def format_cli(report: SuiteReport) -> str:
    raw_gate = _report_gate(report)
    if raw_gate == "green":
        gate = "GREEN"
    elif raw_gate == "red":
        gate = "RED"
    elif raw_gate == "needs review":
        gate = "NEEDS REVIEW"
    else:
        gate = "NOT SCORED"
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
        if task.passed is True and getattr(task, "review", False):
            lines.append(f"  REVIEW  {task.task_id} — {UNSURE_REVIEW}")
            lines.extend(f"       {item}" for item in _extra_source_lines(task))
            continue
        if task.passed is True:
            lines.append(f"  PASS  {task.task_id}")
            for warning in _task_warnings(task):
                if warning == UNSURE_REVIEW:
                    continue
                lines.append(f"       {warning}")
            lines.extend(f"       {item}" for item in _extra_source_lines(task))
            continue
        if task.passed is None:
            lines.append(f"  NOT SCORED  {task.task_id}")
            continue
        why = _task_fail_line(task)
        lines.append(f"  FAIL  {task.task_id} — {why}")
        lines.extend(f"       {item}" for item in _extra_source_lines(task))
        if task.advice:
            lines.append(f"       why:  {task.advice.why}")
            lines.append(f"       fix:  {task.advice.change}")
    lines.append("")
    if raw_gate == "needs review":
        unsure = ", ".join(t.task_id for t in report.tasks if getattr(t, "review", False))
        lines.append(f"Gate needs review. Unsure tasks: {unsure}")
    elif report.passed is True:
        lines.append("Gate is green.")
    elif report.passed is None:
        lines.append("Quality was not scored.")
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
    raw_gate = _report_gate(report)
    if raw_gate == "green":
        gate = "GREEN"
        emoji = "🟢"
    elif raw_gate == "red":
        gate = "RED"
        emoji = "🔴"
    elif raw_gate == "needs review":
        gate = "NEEDS REVIEW"
        emoji = "⚪"
    else:
        gate = "NOT SCORED"
        emoji = "⚪"
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
        if task.passed is True and getattr(task, "review", False):
            result = "review"
        elif task.passed is True:
            result = "pass"
        elif task.passed is False:
            result = "FAIL"
        else:
            result = "not scored"
        if task.passed is False:
            what = _task_fail_line(task)
            extra = "; ".join(task.failures[1:]) if len(task.failures) > 1 else ""
            if extra:
                what = f"{what}; {extra}"
        else:
            what = _task_happened(task)
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
