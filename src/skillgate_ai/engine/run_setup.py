"""Run an eval suite through a harness and score every task."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from skillgate_ai.engine.models import EvalProgress, TaskReport
from skillgate_ai.engine.run_progress import _emit_progress
from skillgate_ai.engine.task import task_timeout_sec
from skillgate_ai.errors import IngestError, SuiteError
from skillgate_ai.harness import Harness
from skillgate_ai.ingest import Skill, ingest_skill, ingest_skills
from skillgate_ai.judge import Judge, default_judge
from skillgate_ai.suite import SuiteSpec, load_suite


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
