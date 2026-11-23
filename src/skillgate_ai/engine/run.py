"""Run an eval suite through a harness and score every task."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from skillgate_ai.advice import advise_suite
from skillgate_ai.engine.models import (
    KILL_FAILURE,
    EvalProgress,
    SuiteReport,
    TaskProgress,
    TaskReport,
)
from skillgate_ai.engine.task import _run_task, _skipped_report, task_timeout_sec
from skillgate_ai.errors import (
    IngestError,
    SuiteError,
)
from skillgate_ai.harness import (
    Harness,
)
from skillgate_ai.ingest import Skill, ingest_skill, ingest_skills
from skillgate_ai.judge import Judge, default_judge
from skillgate_ai.live import RunControl
from skillgate_ai.sandbox import open_sandbox
from skillgate_ai.suite import SuiteSpec, TaskSpec, load_suite


def _load_eval_inputs(
    suite_path: str | Path | None,
    spec: SuiteSpec | None,
    project_root: Path,
    skill_override: str | Path | None,
    strict_ingest: bool,
) -> tuple[SuiteSpec, Path, list[Skill], list[str | Path]]:
    if spec is None:
        if suite_path is None:
            raise SuiteError("No eval suite given.")
        spec, suite_dir = load_suite(suite_path)
    else:
        suite_dir = project_root / "evals"
        if not suite_dir.is_dir():
            suite_dir = project_root
    root = project_root
    skill_rel = skill_override or spec.skill
    skill_paths: list[str | Path] = []
    primary = _resolve_path(root, suite_dir, str(skill_rel))
    skill_paths.append(primary)
    for extra in spec.skills:
        resolved = _resolve_path(root, suite_dir, extra)
        if resolved not in skill_paths:
            skill_paths.append(resolved)
    skills = ingest_skills(skill_paths, strict=strict_ingest)
    return spec, suite_dir, skills, skill_paths


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


def _eval_bootstrap(
    suite_path: str | Path | None,
    spec: SuiteSpec | None,
    project_root: Path,
    skill_override: str | Path | None,
    strict_ingest: bool,
    judge: Judge | None,
    pack_fingerprint: str | None,
    pack_case_ids: tuple[str, ...] | list[str] | None,
) -> tuple[
    Judge,
    SuiteSpec,
    Path,
    list[Skill],
    list[str | Path],
    Path,
    Skill | None,
    str | None,
    tuple[str, ...] | None,
]:
    outcome_judge = judge if judge is not None else default_judge()
    spec, suite_dir, skills, skill_paths = _load_eval_inputs(
        suite_path, spec, project_root, skill_override, strict_ingest
    )
    root = project_root
    reference = _reference_twin(root, skills[0] if skills else None)
    stamp_fp, stamp_ids = _resolve_pack_stamp(
        skills[0].path if skills else None,
        spec,
        pack_fingerprint=pack_fingerprint,
        pack_case_ids=pack_case_ids,
    )
    return outcome_judge, spec, suite_dir, skills, skill_paths, root, reference, stamp_fp, stamp_ids


def _eval_run_preamble(
    spec: SuiteSpec,
    skills: list[Skill],
    prior_reports: list[TaskReport] | None,
    start_index: int,
    timeout_override: int | None,
    on_progress: Callable[[EvalProgress], None] | None,
    harness: Harness,
    config: dict | None,
    stamp_fp: str | None,
    stamp_ids: tuple[str, ...] | None,
) -> tuple[list[TaskReport], int, str, int | None]:
    reports: list[TaskReport] = list(prior_reports or [])
    start_index = max(0, int(start_index or 0))
    if start_index > len(reports):
        reports = reports[:start_index]
    skill_name = skills[0].name if skills else spec.skill
    timeout_effective = (
        task_timeout_sec(spec.tasks[0], spec, timeout_override=timeout_override)
        if spec.tasks
        else timeout_override
    )
    _emit_progress(
        on_progress,
        spec=spec,
        skill=skill_name,
        harness=harness,
        reports=reports,
        config=config,
        pack_fingerprint=stamp_fp,
        pack_case_ids=stamp_ids,
    )
    return reports, start_index, skill_name, timeout_effective


def _run_tasks_loop(
    spec: SuiteSpec,
    *,
    skills: list[Skill],
    harness: Harness,
    sandbox_kind: str,
    docker_image: str,
    root: Path,
    suite_dir: Path,
    reference: Skill | None,
    failed_prompts: list[str],
    reports: list[TaskReport],
    start_index: int,
    max_tasks: int | None,
    timeout_override: int | None,
    control: RunControl | None,
    outcome_judge: Judge,
    config: dict | None,
    on_progress: Callable[[EvalProgress], None] | None,
    skill_name: str,
    stamp_fp: str | None,
    stamp_ids: tuple[str, ...] | None,
) -> tuple[list[TaskReport], bool, int | None]:
    sliced = False
    next_task_index: int | None = None
    tasks_this_slice = 0
    for index, task in enumerate(spec.tasks):
        if index < start_index:
            continue
        if control is not None and control.kill_requested:
            break
        sandbox = open_sandbox(sandbox_kind, docker_image)
        try:
            reports.append(
                _run_task(
                    task=task,
                    spec=spec,
                    skills=skills,
                    harness=harness,
                    sandbox=sandbox,
                    root=root,
                    suite_dir=suite_dir,
                    reference=reference,
                    sibling_prompts=failed_prompts,
                    timeout_override=timeout_override,
                    control=control,
                    judge=outcome_judge,
                    run_config=config,
                )
            )
        finally:
            sandbox.close()
        tasks_this_slice += 1
        _emit_progress(
            on_progress,
            spec=spec,
            skill=skill_name,
            harness=harness,
            reports=reports,
            config=config,
            pack_fingerprint=stamp_fp,
            pack_case_ids=stamp_ids,
        )
        if max_tasks is not None and tasks_this_slice >= max_tasks and index + 1 < len(spec.tasks):
            sliced = True
            next_task_index = index + 1
            break
    return reports, sliced, next_task_index


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


def run_eval(
    suite_path: str | Path | None = None,
    *,
    harness: Harness,
    sandbox_kind: str,
    docker_image: str,
    project_root: Path,
    skill_override: str | Path | None = None,
    spec: SuiteSpec | None = None,
    on_progress: Callable[[EvalProgress], None] | None = None,
    run_id: str = "",
    timeout_override: int | None = None,
    config: dict | None = None,
    control: RunControl | None = None,
    start_index: int = 0,
    max_tasks: int | None = None,
    prior_reports: list[TaskReport] | None = None,
    pack_fingerprint: str | None = None,
    pack_case_ids: tuple[str, ...] | list[str] | None = None,
    judge: Judge | None = None,
    strict_ingest: bool = True,
) -> SuiteReport:
    """Run every task. Hosted slice/poller kwargs are not part of the public gate."""
    (
        outcome_judge,
        spec,
        suite_dir,
        skills,
        skill_paths,
        root,
        reference,
        stamp_fp,
        stamp_ids,
    ) = _eval_bootstrap(
        suite_path,
        spec,
        project_root,
        skill_override,
        strict_ingest,
        judge,
        pack_fingerprint,
        pack_case_ids,
    )
    failed_prompts = [t.prompt for t in spec.tasks if t.expect_skill]
    reports, start_index, skill_name, timeout_effective = _eval_run_preamble(
        spec,
        skills,
        prior_reports,
        start_index,
        timeout_override,
        on_progress,
        harness,
        config,
        stamp_fp,
        stamp_ids,
    )
    reports, sliced, next_task_index = _run_tasks_loop(
        spec,
        skills=skills,
        harness=harness,
        sandbox_kind=sandbox_kind,
        docker_image=docker_image,
        root=root,
        suite_dir=suite_dir,
        reference=reference,
        failed_prompts=failed_prompts,
        reports=reports,
        start_index=start_index,
        max_tasks=max_tasks,
        timeout_override=timeout_override,
        control=control,
        outcome_judge=outcome_judge,
        config=config,
        on_progress=on_progress,
        skill_name=skill_name,
        stamp_fp=stamp_fp,
        stamp_ids=stamp_ids,
    )
    return _eval_finish(
        spec,
        skills,
        control=control,
        sliced=sliced,
        next_task_index=next_task_index,
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


def _suite_passed(tasks: list[TaskReport]) -> bool | None:
    if any(task.passed is False for task in tasks):
        return False
    if any(task.passed is None for task in tasks):
        return None
    return True


def _resolve_path(root: Path, suite_dir: Path, rel: str) -> Path:
    path = Path(rel)
    if path.is_absolute():
        return path
    for base in (root, suite_dir, suite_dir.parent):
        candidate = (base / path).resolve()
        if candidate.exists():
            return candidate
    return (root / path).resolve()


def _reference_twin(root: Path, skill: Skill | None) -> Skill | None:
    for base in (root, *root.parents):
        twin = base / "skills" / "pdf"
        if not skill or not twin.is_dir():
            continue
        if twin.resolve() == skill.path.resolve():
            return None
        try:
            return ingest_skill(twin)
        except IngestError:
            continue
    return None


def _resolve_pack_stamp(
    skill_path: Path | None,
    spec: SuiteSpec,
    *,
    pack_fingerprint: str | None,
    pack_case_ids: tuple[str, ...] | list[str] | None,
) -> tuple[str | None, tuple[str, ...] | None]:
    if pack_fingerprint:
        ids = tuple(pack_case_ids) if pack_case_ids else tuple(task.id for task in spec.tasks)
        return pack_fingerprint, ids
    if skill_path is None:
        return None, None
    from skillgate_ai.case_pack import trust_suite_for_skill

    trust = trust_suite_for_skill(skill_path)
    if trust is None:
        return None, None
    if tuple(task.id for task in spec.tasks) != trust.case_ids:
        return None, None
    return trust.fingerprint, trust.case_ids


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
