"""Per-case path steps and optional token/step budgets.

Token counts stay on the existing harness ``Usage`` shape — this module never
estimates dollars or tokens. Path compactness is step count from OTLP spans
(``tool.*`` / ``skill.select``) with a ``$ `` / ``changed `` transcript fallback.

Budgets are optional. Unset keys are informational. A pinned positive integer
that is exceeded (or fail-closed when the run cannot prove it stayed under)
is a Gate block, not a Jev Fail.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ValidationError, field_validator

STATUS_ERROR = 2
_CHANGED_LINE = re.compile(r"^changed\s+\S+")

REASON_TOKEN_OVER = "This case went over its token budget."
REASON_PATH_OVER = "This case took more steps than its path budget."
REASON_BOTH_OVER = "This case went over its token and path budgets."
REASON_TOKEN_CLOSED = "This case has a token budget, but the run did not report tokens."
REASON_PATH_CLOSED = "This case has a step budget, but the run did not record a path."
REASON_MULTI = "{n} cases went over a pinned budget."
REASON_CLEARED = "This Dataset passed."

MetricsStatus = Literal["info", "ok", "fail"]


class CaseBudgets(BaseModel):
    tokens_total: int | None = None
    max_steps: int | None = None

    @field_validator("tokens_total", "max_steps", mode="before")
    @classmethod
    def _empty_unset(cls, value: object) -> object:
        if value is None or value == "":
            return None
        return value

    @field_validator("tokens_total", "max_steps")
    @classmethod
    def _positive(cls, value: int | None) -> int | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("Budget must be a positive integer, or left empty.")
        return value

    def is_empty(self) -> bool:
        return self.tokens_total is None and self.max_steps is None

    def to_sparse_dict(self) -> dict[str, int]:
        data: dict[str, int] = {}
        if self.tokens_total is not None:
            data["tokens_total"] = self.tokens_total
        if self.max_steps is not None:
            data["max_steps"] = self.max_steps
        return data


def parse_budgets(raw: CaseBudgets | dict[str, Any] | None) -> CaseBudgets | None:
    """Parse a budgets map. Empty → None. Non-positive values raise."""
    if raw is None:
        return None
    if isinstance(raw, CaseBudgets):
        return None if raw.is_empty() else raw
    if not isinstance(raw, dict):
        return None
    data = {
        "tokens_total": raw.get("tokens_total"),
        "max_steps": raw.get("max_steps"),
    }
    try:
        budgets = CaseBudgets.model_validate(data)
    except ValidationError as exc:
        raise ValueError("Budget must be a positive integer, or left empty.") from exc
    return None if budgets.is_empty() else budgets


def merge_budgets(
    suite: CaseBudgets | dict[str, Any] | None,
    case: CaseBudgets | dict[str, Any] | None,
) -> CaseBudgets | None:
    """Case keys overlay suite defaults. Empty result is None."""
    suite_b = _as_budgets(suite)
    case_b = _as_budgets(case)
    tokens = case_b.tokens_total if case_b.tokens_total is not None else suite_b.tokens_total
    steps = case_b.max_steps if case_b.max_steps is not None else suite_b.max_steps
    out = CaseBudgets(tokens_total=tokens, max_steps=steps)
    return None if out.is_empty() else out


def count_path_steps(
    spans: list[dict[str, Any]] | None = None,
    transcript: str | None = None,
) -> tuple[int, int, bool]:
    """Return ``(steps, errors, had_path)``.

    Steps count ``skill.select`` and ``tool.*`` spans (not ``eval.check``).
    When none of those exist, fall back to ``$ `` / ``changed `` lines.
    """
    records = list(spans) if spans else []
    text = transcript or ""
    # Root eval.check (and assistant spans) are not steps. If the provided
    # list has no tool/select spans, rebuild from transcript JSONL — same
    # order as countHarnessCommands — before the `$ `/changed fallback.
    if not any(_is_path_span(span) for span in records) and text.strip():
        from skillgate_ai.spans import spans_from_jsonl

        rebuilt = spans_from_jsonl(text)
        if any(_is_path_span(span) for span in rebuilt):
            records = rebuilt
    path_spans = [span for span in records if _is_path_span(span)]
    errors = sum(1 for span in records if _is_error_span(span))
    if path_spans:
        return len(path_spans), errors, True
    fallback = _command_line_count(text)
    return fallback, errors, fallback > 0


def evaluate_task_metrics(
    usage: dict[str, Any] | None,
    spans: list[dict[str, Any]] | None,
    transcript: str | None,
    budgets: CaseBudgets | dict[str, Any] | None,
) -> dict[str, Any]:
    """Per-case metrics dict for ``TaskReport`` / Gate."""
    effective = _as_budgets(budgets)
    if effective.is_empty():
        effective_or_none: CaseBudgets | None = None
    else:
        effective_or_none = effective
    steps, errors, had_path = count_path_steps(spans, transcript)
    reasons: list[str] = []
    token_fail = False
    path_fail = False
    token_closed = False
    path_closed = False

    if effective.tokens_total is not None:
        tokens_total = _tokens_total(usage)
        if tokens_total is None:
            token_fail = True
            token_closed = True
            reasons.append(REASON_TOKEN_CLOSED)
        elif tokens_total > effective.tokens_total:
            token_fail = True
            reasons.append(REASON_TOKEN_OVER)

    if effective.max_steps is not None:
        if not had_path:
            path_fail = True
            path_closed = True
            reasons.append(REASON_PATH_CLOSED)
        elif steps > effective.max_steps:
            path_fail = True
            reasons.append(REASON_PATH_OVER)

    if token_fail and path_fail and not token_closed and not path_closed:
        reasons = [REASON_BOTH_OVER]

    if effective_or_none is None:
        status: MetricsStatus = "info"
    elif token_fail or path_fail:
        status = "fail"
    else:
        status = "ok"

    payload: dict[str, Any] = {
        "path": {"steps": steps, "errors": errors, "had_path": had_path},
        "budgets": (
            None
            if effective_or_none is None
            else {
                "tokens_total": effective_or_none.tokens_total,
                "max_steps": effective_or_none.max_steps,
            }
        ),
        "status": status,
        "reasons": reasons,
        "blocking": status == "fail",
    }
    return payload


def metrics_blocking(report: dict[str, Any] | None) -> bool:
    """True when any task has a pinned-budget fail. Missing metrics = not blocking."""
    return bool(_blocking_tasks(report))


def budget_gate_reason(report: dict[str, Any] | None) -> str:
    fails = _blocking_tasks(report)
    if not fails:
        return REASON_CLEARED
    if len(fails) > 1:
        return REASON_MULTI.format(n=len(fails))
    reasons = _task_reasons(fails[0])
    tokenish = any(_is_token_reason(item) for item in reasons)
    pathish = any(_is_path_reason(item) for item in reasons)
    if tokenish and pathish:
        if len(reasons) == 1:
            return reasons[0]
        closed_only = all(
            item in {REASON_TOKEN_CLOSED, REASON_PATH_CLOSED} for item in reasons
        )
        if closed_only and len(reasons) == 1:
            return reasons[0]
        if REASON_BOTH_OVER in reasons:
            return REASON_BOTH_OVER
        if not any(item in {REASON_TOKEN_CLOSED, REASON_PATH_CLOSED} for item in reasons):
            return REASON_BOTH_OVER
        return reasons[0]
    if reasons:
        return reasons[0]
    return REASON_TOKEN_OVER


def suite_metrics_summary(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    fails = [
        str(task.get("id") or task.get("task_id") or "")
        for task in tasks
        if _task_blocking(task)
    ]
    fails = [item for item in fails if item]
    if fails:
        status: MetricsStatus = "fail"
    elif any(_task_status(task) == "ok" for task in tasks):
        status = "ok"
    else:
        status = "info"
    steps = 0
    errors = 0
    had_path = False
    saw_path = False
    for task in tasks:
        metrics = task.get("metrics") if isinstance(task, dict) else None
        path = metrics.get("path") if isinstance(metrics, dict) else None
        if not isinstance(path, dict):
            continue
        saw_path = True
        raw_steps = path.get("steps")
        raw_errors = path.get("errors")
        if isinstance(raw_steps, (int, float)):
            steps += int(raw_steps)
        if isinstance(raw_errors, (int, float)):
            errors += int(raw_errors)
        if path.get("had_path") is True or (isinstance(raw_steps, (int, float)) and int(raw_steps) > 0):
            had_path = True
    summary: dict[str, Any] = {"budget_fails": fails, "status": status}
    if saw_path:
        summary["path"] = {"steps": steps, "errors": errors, "had_path": had_path}
    return summary


def _as_budgets(raw: CaseBudgets | dict[str, Any] | None) -> CaseBudgets:
    if raw is None:
        return CaseBudgets()
    if isinstance(raw, CaseBudgets):
        return raw
    if not isinstance(raw, dict):
        return CaseBudgets()
    data = {
        "tokens_total": raw.get("tokens_total"),
        "max_steps": raw.get("max_steps"),
    }
    try:
        return CaseBudgets.model_validate(data)
    except Exception:
        return CaseBudgets()


def _tokens_total(usage: dict[str, Any] | None) -> int | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get("tokens_total")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def _is_path_span(span: dict[str, Any]) -> bool:
    name = str(span.get("name") or "")
    return name == "skill.select" or name.startswith("tool.")


def _is_error_span(span: dict[str, Any]) -> bool:
    if str(span.get("name") or "") == "gen_ai.error":
        return True
    status = span.get("status")
    if not isinstance(status, dict):
        return False
    code = status.get("code")
    return code == STATUS_ERROR or code == str(STATUS_ERROR)


def _command_line_count(transcript: str) -> int:
    count = 0
    for line in transcript.replace("\r\n", "\n").split("\n"):
        text = line.strip()
        if text.startswith("$ ") or _CHANGED_LINE.match(text):
            count += 1
    return count


def _blocking_tasks(report: dict[str, Any] | None) -> list[dict[str, Any]]:
    tasks = (report or {}).get("tasks") or []
    out: list[dict[str, Any]] = []
    for task in tasks:
        if isinstance(task, dict) and _task_blocking(task):
            out.append(task)
    return out


def _task_blocking(task: dict[str, Any]) -> bool:
    metrics = task.get("metrics")
    if not isinstance(metrics, dict):
        return False
    if metrics.get("blocking") is True:
        return True
    return metrics.get("status") == "fail"


def _task_status(task: dict[str, Any]) -> str | None:
    metrics = task.get("metrics")
    if not isinstance(metrics, dict):
        return None
    status = metrics.get("status")
    return str(status) if status is not None else None


def _task_reasons(task: dict[str, Any]) -> list[str]:
    metrics = task.get("metrics")
    if not isinstance(metrics, dict):
        return []
    raw = metrics.get("reasons") or []
    return [str(item) for item in raw if str(item).strip()]


def _is_token_reason(reason: str) -> bool:
    return "token" in reason.lower()


def _is_path_reason(reason: str) -> bool:
    lower = reason.lower()
    return "path budget" in lower or "step budget" in lower or "steps than" in lower
