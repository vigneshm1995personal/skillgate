"""Run an eval suite through a harness and score every task."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.advice import advise_suite
from skillgate_ai.engine.models import KILL_FAILURE, SuiteReport, TaskReport
from skillgate_ai.engine.task import _skipped_report
from skillgate_ai.harness import Harness
from skillgate_ai.ingest import Skill
from skillgate_ai.live import RunControl
from skillgate_ai.suite import SuiteSpec


def _fill_killed(reports: list[TaskReport], spec: SuiteSpec) -> None:
    finished = {item.task_id for item in reports}
    order = {task.id: index for index, task in enumerate(spec.tasks)}
    for task in spec.tasks:
        if task.id not in finished:
            reports.append(_skipped_report(task, KILL_FAILURE))
    reports.sort(key=lambda item: order.get(item.task_id, 0))


def _sliced_report(
    spec: SuiteSpec,
    skills: list[Skill],
    *,
    harness: Harness,
    sandbox_kind: str,
    reports: list[TaskReport],
    skill_paths: list[str | Path],
    config: dict | None,
    timeout_effective: int | None,
    stamp_fp: str | None,
    stamp_ids: tuple[str, ...] | None,
    next_task_index: int,
) -> SuiteReport:
    return SuiteReport(
        suite=spec.suite,
        title=spec.title or spec.suite,
        skill=skills[0].name if skills else spec.skill,
        harness=harness.name,
        sandbox=sandbox_kind,
        passed=False,
        tasks=reports,
        skill_description=skills[0].description if skills else "",
        advice=None,
        skill_path=str(skill_paths[0]) if skill_paths else "",
        config=config,
        timeout_effective=timeout_effective,
        incomplete=True,
        next_task_index=next_task_index,
        pack_fingerprint=stamp_fp,
        pack_case_ids=stamp_ids,
    )


def _eval_finish(
    spec: SuiteSpec,
    skills: list[Skill],
    *,
    control: RunControl | None,
    sliced: bool,
    next_task_index: int | None,
    harness: Harness,
    sandbox_kind: str,
    reports: list[TaskReport],
    skill_paths: list[str | Path],
    config: dict | None,
    timeout_effective: int | None,
    stamp_fp: str | None,
    stamp_ids: tuple[str, ...] | None,
    reference: Skill | None,
) -> SuiteReport:
    if control is not None and control.kill_requested and not sliced:
        _fill_killed(reports, spec)
    if sliced:
        assert next_task_index is not None  # noqa: S101 - type-narrowing invariant guaranteed by the branch above
        return _sliced_report(
            spec,
            skills,
            harness=harness,
            sandbox_kind=sandbox_kind,
            reports=reports,
            skill_paths=skill_paths,
            config=config,
            timeout_effective=timeout_effective,
            stamp_fp=stamp_fp,
            stamp_ids=stamp_ids,
            next_task_index=next_task_index,
        )
    return _complete_suite_report(
        spec,
        skills,
        harness=harness,
        sandbox_kind=sandbox_kind,
        reports=reports,
        skill_paths=skill_paths,
        config=config,
        timeout_effective=timeout_effective,
        stamp_fp=stamp_fp,
        stamp_ids=stamp_ids,
        reference=reference,
    )


def _complete_suite_report(
    spec: SuiteSpec,
    skills: list[Skill],
    *,
    harness: Harness,
    sandbox_kind: str,
    reports: list[TaskReport],
    skill_paths: list[str | Path],
    config: dict | None,
    timeout_effective: int | None,
    stamp_fp: str | None,
    stamp_ids: tuple[str, ...] | None,
    reference: Skill | None,
) -> SuiteReport:
    passed = _suite_passed(reports)
    primary_skill = skills[0] if skills else None
    suite_advice = (
        advise_suite(primary_skill, reports, reference=reference) if primary_skill else None
    )
    report = SuiteReport(
        suite=spec.suite,
        title=spec.title or spec.suite,
        skill=skills[0].name if skills else spec.skill,
        harness=harness.name,
        sandbox=sandbox_kind,
        passed=passed,
        tasks=reports,
        skill_description=skills[0].description if skills else "",
        advice=suite_advice,
        skill_path=str(skill_paths[0]) if skill_paths else "",
        config=config,
        timeout_effective=timeout_effective,
        pack_fingerprint=stamp_fp,
        pack_case_ids=stamp_ids,
    )
    return report


def _suite_passed(tasks: list[TaskReport]) -> bool | None:
    if any(task.passed is False for task in tasks):
        return False
    if any(task.passed is None for task in tasks):
        return None
    return True
