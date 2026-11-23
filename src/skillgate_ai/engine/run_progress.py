"""Run an eval suite through a harness and score every task."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from skillgate_ai.engine.models import EvalProgress, TaskProgress, TaskReport
from skillgate_ai.harness import Harness
from skillgate_ai.suite import SuiteSpec, TaskSpec


def _emit_progress(
    on_progress: Callable[[EvalProgress], None] | None,
    *,
    spec: SuiteSpec,
    skill: str,
    harness: Harness,
    reports: list[TaskReport],
    config: dict | None = None,
    running_task: TaskSpec | None = None,
    running_spans: list[dict[str, Any]] | None = None,
    running_transcript: str = "",
    pack_fingerprint: str | None = None,
    pack_case_ids: tuple[str, ...] | list[str] | None = None,
) -> None:
    if on_progress is None:
        return
    on_progress(
        _eval_progress(
            spec=spec,
            skill=skill,
            harness=harness,
            reports=reports,
            config=config,
            running_task=running_task,
            running_spans=running_spans,
            running_transcript=running_transcript,
            pack_fingerprint=pack_fingerprint,
            pack_case_ids=pack_case_ids,
        )
    )


def _eval_progress(
    *,
    spec: SuiteSpec,
    skill: str,
    harness: Harness,
    reports: list[TaskReport],
    config: dict | None = None,
    running_task: TaskSpec | None = None,
    running_spans: list[dict[str, Any]] | None = None,
    running_transcript: str = "",
    pack_fingerprint: str | None = None,
    pack_case_ids: tuple[str, ...] | list[str] | None = None,
) -> EvalProgress:
    finished = {item.task_id: item for item in reports}
    completed_count = len(reports)
    tasks: list[TaskProgress] = []
    current_task_id: str | None = None
    force_running_id = running_task.id if running_task is not None else None
    for index, task in enumerate(spec.tasks):
        done = finished.get(task.id)
        if done is not None:
            tasks.append(
                TaskProgress(
                    task_id=task.id,
                    prompt=task.prompt,
                    status="done",
                    passed=done.passed,
                    failures=list(done.failures),
                    scores=list(done.scores),
                    skipped=done.skipped,
                    transcript=done.transcript,
                    spans=getattr(done, "spans", None),
                    judge=done.judge,
                    metrics=getattr(done, "metrics", None),
                    usage=getattr(done, "usage", None),
                    expect_skill=done.expect_skill,
                    selected_skill=done.selected_skill,
                    review=bool(getattr(done, "review", False)),
                )
            )
            continue
        is_running = (force_running_id is not None and task.id == force_running_id) or (
            force_running_id is None and index == completed_count
        )
        if is_running:
            current_task_id = task.id
            tasks.append(
                TaskProgress(
                    task_id=task.id,
                    prompt=task.prompt,
                    status="running",
                    transcript=running_transcript if task.id == force_running_id else "",
                    spans=running_spans if task.id == force_running_id else None,
                    expect_skill=task.expect_skill,
                )
            )
        else:
            tasks.append(
                TaskProgress(
                    task_id=task.id,
                    prompt=task.prompt,
                    status="queued",
                    expect_skill=task.expect_skill,
                )
            )
    return EvalProgress(
        suite=spec.suite,
        title=spec.title or spec.suite,
        skill=skill,
        harness=harness.name,
        task_count=len(spec.tasks),
        completed_count=completed_count,
        current_task_id=current_task_id,
        tasks=tasks,
        config=config,
        pack_fingerprint=pack_fingerprint,
        pack_case_ids=tuple(pack_case_ids) if pack_case_ids else None,
    )
