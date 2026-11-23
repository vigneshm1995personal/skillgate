"""Human-readable reports for CLI and GitHub Actions."""

from __future__ import annotations

from skillgate_ai.engine import SuiteReport
from skillgate_ai.harness import is_live_harness


def _report_gate(report: SuiteReport) -> str:
    if report.passed is False:
        return "red"
    if report.passed is None:
        return "not scored"
    if any(getattr(task, "review", False) for task in report.tasks):
        return "needs review"
    return "green"


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


def _scoring_endpoint(report: SuiteReport) -> str | None:
    for task in report.tasks:
        judge = task.judge if isinstance(task.judge, dict) else None
        if not isinstance(judge, dict):
            continue
        endpoint = judge.get("scoring_endpoint")
        if isinstance(endpoint, str) and endpoint.strip():
            return endpoint.strip()
    return None
