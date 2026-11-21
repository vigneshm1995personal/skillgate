"""Run an eval suite through a harness and score every task."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from skillgate_ai.advice import FixAdvice
from skillgate_ai.scorers import Score

SKIP_FAILURE = "Skipped by user"

KILL_FAILURE = "Killed by user"


@dataclass
class TaskReport:
    task_id: str
    prompt: str
    expect_skill: str | None
    passed: bool | None
    scores: list[Score]
    selected_skill: str | None
    failures: list[str] = field(default_factory=list)
    transcript: str = ""
    stderr: str = ""
    returncode: int | None = None
    files: list[dict[str, str]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)
    advice: FixAdvice | None = None
    skipped: bool = False
    usage: dict[str, Any] | None = None
    judge: dict[str, Any] | None = None
    spans: list[dict[str, Any]] | None = None
    metrics: dict[str, Any] | None = None
    model: str | None = None
    review: bool = False

    def failed_scorers(self) -> list[Score]:
        return [s for s in self.scores if not s.passed]


@dataclass
class TaskProgress:
    task_id: str
    prompt: str
    status: str  # queued | running | done
    passed: bool | None = None
    failures: list[str] = field(default_factory=list)
    scores: list[Score] = field(default_factory=list)
    skipped: bool = False
    transcript: str = ""
    judge: dict[str, Any] | None = None
    spans: list[dict[str, Any]] | None = None
    metrics: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    expect_skill: str | None = None
    selected_skill: str | None = None
    review: bool = False


@dataclass
class EvalProgress:
    suite: str
    title: str
    skill: str
    harness: str
    task_count: int
    completed_count: int
    current_task_id: str | None
    tasks: list[TaskProgress]
    config: dict | None = None
    pack_fingerprint: str | None = None
    pack_case_ids: tuple[str, ...] | None = None


@dataclass
class SuiteReport:
    suite: str
    title: str
    skill: str
    harness: str
    sandbox: str
    passed: bool | None
    tasks: list[TaskReport]
    note: str | None = None
    skill_description: str = ""
    advice: FixAdvice | None = None
    skill_path: str = ""
    config: dict | None = None
    timeout_effective: int | None = None
    incomplete: bool = False
    next_task_index: int | None = None
    sandbox_poll: dict | None = None
    pack_fingerprint: str | None = None
    pack_case_ids: tuple[str, ...] | None = None

    @property
    def passed_count(self) -> int:
        return sum(1 for t in self.tasks if t.passed)

    @property
    def failed_tasks(self) -> list[TaskReport]:
        return [t for t in self.tasks if t.passed is False]

    @property
    def usage_totals(self) -> dict[str, Any] | None:
        rows = [task.usage for task in self.tasks if task.usage]
        if not rows:
            return None

        def total(key: str, *, as_float: bool = False) -> float | int | None:
            values = [row[key] for row in rows if row.get(key) is not None]
            if not values:
                return None
            summed = sum(values)
            return round(summed, 6) if as_float else int(summed)

        totals = {
            "tokens_in": total("tokens_in"),
            "tokens_out": total("tokens_out"),
            "tokens_total": total("tokens_total"),
            "cost_usd": total("cost_usd", as_float=True),
            "agent_cost_usd": total("agent_cost_usd", as_float=True),
            "judge_cost_usd": total("judge_cost_usd", as_float=True),
        }
        totals = {key: value for key, value in totals.items() if value is not None}
        labels = {row.get("agent_cost_label") for row in rows if row.get("agent_cost_label")}
        if len(labels) == 1:
            totals["agent_cost_label"] = next(iter(labels))
        if totals.get("tokens_total") and totals.get("cost_usd") is None:
            if totals.get("agent_cost_label"):
                pass
            else:
                totals["cost_unknown"] = True
        return totals or None
