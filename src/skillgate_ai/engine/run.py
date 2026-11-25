"""Run an eval suite through a harness and score every task.

Re-export shim. Code lives in the submodules listed below. Patching a name on this
shim does not affect code inside the package; patch the submodule that defines it.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from skillgate_ai.engine.models import EvalProgress, SuiteReport, TaskReport
from skillgate_ai.engine.run_finish import _complete_suite_report as _complete_suite_report
from skillgate_ai.engine.run_finish import _eval_finish as _eval_finish
from skillgate_ai.engine.run_finish import _fill_killed as _fill_killed
from skillgate_ai.engine.run_finish import _sliced_report as _sliced_report
from skillgate_ai.engine.run_finish import _suite_passed as _suite_passed
from skillgate_ai.engine.run_progress import _emit_progress as _emit_progress
from skillgate_ai.engine.run_progress import _eval_progress as _eval_progress
from skillgate_ai.engine.run_setup import _eval_bootstrap as _eval_bootstrap
from skillgate_ai.engine.run_setup import _eval_run_preamble as _eval_run_preamble
from skillgate_ai.engine.run_setup import _load_eval_inputs as _load_eval_inputs
from skillgate_ai.engine.run_setup import _reference_twin as _reference_twin
from skillgate_ai.engine.run_setup import _resolve_pack_stamp as _resolve_pack_stamp
from skillgate_ai.engine.run_setup import _resolve_path as _resolve_path
from skillgate_ai.engine.task import _run_task
from skillgate_ai.harness import Harness
from skillgate_ai.ingest import Skill
from skillgate_ai.judge import Judge
from skillgate_ai.live import RunControl
from skillgate_ai.sandbox import open_sandbox
from skillgate_ai.suite import SuiteSpec


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
