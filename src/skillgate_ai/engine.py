"""Run an eval suite through a harness and score every task."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skillgate_ai.advice import FixAdvice, advise_suite, advise_task
from skillgate_ai.errors import IngestError, SuiteError
from skillgate_ai.harness import Harness, HarnessResult, _write_selection, is_live_harness
from skillgate_ai.ingest import Skill, ingest_skill, ingest_skills
from skillgate_ai.judge import Judge, SkipJudge, default_judge, judge_stamp
from skillgate_ai.live import KILL, CheckAborted, RunControl
from skillgate_ai.observability import breadcrumb_task, report_eval_outcome, set_eval_passed, span
from skillgate_ai.output_match import expected_output_mismatch_reason
from skillgate_ai.pack import resolve_input_file
from skillgate_ai.sandbox import Sandbox, open_sandbox, prepare_workspace
from skillgate_ai.scorers import RunArtifacts, Score, score_task
from skillgate_ai.suite import SuiteSpec, TaskSpec, load_suite

SKIP_FAILURE = "Skipped by user"
KILL_FAILURE = "Killed by user"


@dataclass
class TaskReport:
    task_id: str
    prompt: str
    expect_skill: str | None
    passed: bool
    scores: list[Score]
    selected_skill: str | None
    failures: list[str] = field(default_factory=list)
    transcript: str = ""
    stderr: str = ""
    returncode: int | None = None
    files: list[dict[str, str]] = field(default_factory=list)
    advice: FixAdvice | None = None
    skipped: bool = False
    usage: dict[str, Any] | None = None
    judge: dict[str, Any] | None = None
    spans: list[dict[str, Any]] | None = None
    metrics: dict[str, Any] | None = None

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
    passed: bool
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
        return [t for t in self.tasks if not t.passed]

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

        return {
            "tokens_in": total("tokens_in"),
            "tokens_out": total("tokens_out"),
            "tokens_total": total("tokens_total"),
            "cost_usd": total("cost_usd", as_float=True),
        }


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
    outcome_judge = judge if judge is not None else default_judge()
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
    skill_paths = []
    primary = _resolve_path(root, suite_dir, str(skill_rel))
    skill_paths.append(primary)
    for extra in spec.skills:
        resolved = _resolve_path(root, suite_dir, extra)
        if resolved not in skill_paths:
            skill_paths.append(resolved)
    skills = ingest_skills(skill_paths, strict=strict_ingest)
    reference = _reference_twin(root, skills[0] if skills else None)
    stamp_fp, stamp_ids = _resolve_pack_stamp(
        skills[0].path if skills else None,
        spec,
        pack_fingerprint=pack_fingerprint,
        pack_case_ids=pack_case_ids,
    )
    failed_prompts = [t.prompt for t in spec.tasks if t.expect_skill]
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
        if (
            max_tasks is not None
            and tasks_this_slice >= max_tasks
            and index + 1 < len(spec.tasks)
        ):
            sliced = True
            next_task_index = index + 1
            break
    if control is not None and control.kill_requested and not sliced:
        finished = {item.task_id for item in reports}
        order = {task.id: index for index, task in enumerate(spec.tasks)}
        for task in spec.tasks:
            if task.id not in finished:
                reports.append(_skipped_report(task, KILL_FAILURE))
        reports.sort(key=lambda item: order.get(item.task_id, 0))
    if sliced:
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
    passed = all(t.passed for t in reports)
    primary_skill = skills[0] if skills else None
    suite_advice = advise_suite(primary_skill, reports, reference=reference) if primary_skill else None
    set_eval_passed(passed)
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
    report_eval_outcome(report, run_id=run_id)
    return report


def task_timeout_sec(
    task: TaskSpec,
    spec: SuiteSpec,
    timeout_override: int | None = None,
) -> int:
    if timeout_override is not None:
        return timeout_override
    env_override = env_task_timeout_sec()
    if env_override is not None:
        return env_override
    return task.timeout_sec or spec.timeout_sec


def env_task_timeout_sec() -> int | None:
    raw = os.environ.get("SKILLGATE_TASK_TIMEOUT_SEC", "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    if value <= 0:
        return None
    return value


def _outcome_judge_outputs(task: TaskSpec, artifacts: RunArtifacts) -> list[dict[str, Any]]:
    from skillgate_ai.case_pack import sniff_output_bytes

    outputs: list[dict[str, Any]] = []
    for spec in task.scorers:
        if spec.type != "task_completion":
            continue
        for item in spec.files:
            dest = artifacts.workspace / item.path
            present = dest.is_file()
            row: dict[str, Any] = {"path": item.path, "present": present}
            if present:
                sniffed = sniff_output_bytes(dest.read_bytes())
                row.update(sniffed)
            outputs.append(row)
    return outputs


def _score_rows(scores: list[Score]) -> list[dict[str, Any]]:
    return [
        {
            "scorer": item.scorer,
            "passed": item.passed,
            "headline": item.headline,
            "detail": item.detail,
        }
        for item in scores
    ]


def _run_outcome_judge(
    task: TaskSpec,
    artifacts: RunArtifacts,
    result: HarnessResult,
    scores: list[Score],
    harness_name: str,
    skill_root: Path | None = None,
    path: dict[str, Any] | None = None,
    judge: Judge | None = None,
) -> tuple[
    dict[str, Any] | None,
    str | None,
    dict[str, Any] | None,
    dict[str, Any] | None,
]:
    """Optional Judge protocol. SkipJudge (default) does not own red/green."""
    if not is_live_harness(harness_name):
        return None, None, None, None
    outcome = judge if judge is not None else SkipJudge()
    golden_payload = None
    actual_payload = None
    if skill_root is not None:
        from skillgate_ai.case_pack import (
            actual_output_state,
            case_for_task,
            golden_state,
            load_case_pack,
        )

        pack = load_case_pack(skill_root)
        case = case_for_task(pack, task.id)
        if case is not None and case.golden is not None:
            golden_payload = golden_state(case.golden, skill_root)
            actual_payload = actual_output_state(
                case.golden.output_path, artifacts.workspace
            )
    outputs = _outcome_judge_outputs(task, artifacts)
    judged = outcome.judge(
        task.prompt,
        outputs,
        result.transcript,
        expect_skill=task.expect_skill,
        selected_skill=result.trigger.selected_skill,
        golden=golden_payload,
        actual_output=actual_payload,
        scores=_score_rows(scores),
        path=path,
        workspace=artifacts.workspace,
        skill_root=skill_root,
    )
    mismatch = expected_output_mismatch_reason(
        golden=golden_payload if isinstance(golden_payload, dict) else None,
        actual=actual_payload if isinstance(actual_payload, dict) else None,
        artifacts=outputs,
    )
    return judged, mismatch, golden_payload, actual_payload


def _apply_mismatch(
    passed: bool,
    failures: list[str],
    mismatch: str | None,
) -> tuple[bool, list[str]]:
    if not mismatch:
        return passed, failures
    if mismatch in failures:
        return False, failures
    return False, [mismatch, *failures]


CORRECTLY_SKIPPED = "Correctly skipped"


def _no_trigger_skipped_judge(judge: Judge | None) -> dict[str, Any]:
    """Output rubric is N/A when the check is 'do not pick a skill'."""
    from skillgate_ai.judge_bank import CHECK_CELL_LABELS, CHECK_CELL_ORDER, SOFT_CELL_LABELS

    stamp = judge_stamp(judge)
    cells = {
        key: {"label": CHECK_CELL_LABELS[key], "choice": CORRECTLY_SKIPPED}
        for key in CHECK_CELL_ORDER
    }
    cells["path_efficiency"] = {
        "label": SOFT_CELL_LABELS["path_efficiency"],
        "choice": CORRECTLY_SKIPPED,
    }
    answers = {key: {"choice": CORRECTLY_SKIPPED} for key in CHECK_CELL_ORDER}
    questions = {
        key: {"instructions": CHECK_CELL_LABELS[key]} for key in CHECK_CELL_ORDER
    }
    return {
        **stamp,
        "status": "skip",
        "passed": None,
        "reasons": [],
        "why": None,
        "answers": answers,
        "cells": cells,
        "warnings": [],
        "questions": questions,
    }


def _live_verdict(
    judge: dict[str, Any] | None,
    expect_skill: str | None,
    *,
    det_passed: bool,
    det_failures: list[str],
    mismatch: str | None = None,
) -> tuple[bool, list[str], dict[str, Any] | None]:
    """Skip leaves det in charge. Errors fail closed. No-trigger keeps det.
    A completed bool ``passed`` overrides, including a low-confidence Pass.
    Gate ``passed`` is the return value. Cell ``passed`` stays on the judge dict."""
    if not isinstance(judge, dict):
        return det_passed, det_failures, judge
    warnings = [
        str(item) for item in (judge.get("warnings") or []) if str(item).strip()
    ]
    stamped = {**judge, "warnings": warnings}
    if expect_skill is None:
        return det_passed, det_failures, stamped
    if judge.get("status") == "error":
        failures = [str(item) for item in (judge.get("reasons") or []) if str(item).strip()]
        if not failures:
            failures = ["OpenAI scoring failed."]
        passed, failures = _apply_mismatch(False, failures, mismatch)
        return passed, failures, stamped
    if judge.get("status") == "skip" or judge.get("passed") is None:
        return det_passed, det_failures, judge
    passed = bool(judge.get("passed"))
    failures = [str(item) for item in (judge.get("reasons") or []) if str(item).strip()]
    if not passed and not failures:
        failures = list(det_failures) or ["OpenAI scoring failed this check."]
    passed, failures = _apply_mismatch(passed, failures, mismatch)
    return passed, failures, stamped


def _seed_skill_selection(workspace: Path, expect_skill: str | None) -> None:
    """Pin a skill for trigger checks. Leave the catalog open for no-trigger."""
    if expect_skill is None:
        target = workspace / ".skillgate" / "selected.json"
        if target.is_file():
            target.unlink()
        return
    _write_selection(workspace, expect_skill)


def _why_expected_output(
    task: TaskSpec,
    golden_payload: dict[str, Any] | None,
    *,
    skill_name: str | None = None,
) -> Any:
    """This check's own expectation for the Fail why-call. Never a sibling golden."""
    if task.expect_skill is None:
        if skill_name:
            label = skill_name.upper() if len(skill_name) <= 4 else skill_name
            return f"No {label} skill triggered"
        return "No skill triggered"
    if isinstance(golden_payload, dict):
        return golden_payload
    for spec in task.scorers:
        for item in spec.files:
            if item.contains:
                return item.contains
        for check in spec.checks:
            if check.contains:
                return check.contains
    return None


def _maybe_explain_fail(
    judge: Judge | None,
    passed: bool,
    failures: list[str],
    judged: dict[str, Any] | None,
    *,
    check: str,
    transcript_tail: str,
    expected_output: Any = None,
    actual_output: Any = None,
) -> dict[str, Any] | None:
    """Ask the scorer for a Fail sentence only after the gate verdict."""
    if passed or judged is None or judge is None:
        return judged
    why = judge.explain_fail(
        list(failures),
        judged=judged,
        check=check,
        transcript_tail=transcript_tail,
        expected_output=expected_output,
        actual_output=actual_output,
    )
    if isinstance(why, str) and why.strip():
        return {**judged, "why": why.strip()}
    return judged


def _run_task(
    *,
    task: TaskSpec,
    spec: SuiteSpec,
    skills: list[Skill],
    harness: Harness,
    sandbox: Sandbox,
    root: Path,
    suite_dir: Path,
    reference: Skill | None = None,
    sibling_prompts: list[str] | None = None,
    timeout_override: int | None = None,
    control: RunControl | None = None,
    judge: Judge | None = None,
) -> TaskReport:
    timeout = task_timeout_sec(task, spec, timeout_override=timeout_override)
    if control is not None:
        sandbox.output_sink = control
        control.begin_task(task.id, task.prompt)
    breadcrumb_task("start", task.id, timeout_sec=timeout)
    ended = False
    try:
        with span("eval.task", task.id, expect_skill=task.expect_skill or ""):
            copies: list[tuple[Path, str]] = []
            skill_root = skills[0].path if skills else None
            if skill_root is not None:
                from skillgate_ai.case_pack import (
                    MISSING_GOLDEN_REASON,
                    task_missing_golden,
                )

                if task_missing_golden(skill_root, task.id):
                    ended = True
                    return TaskReport(
                        task_id=task.id,
                        prompt=task.prompt,
                        expect_skill=task.expect_skill,
                        passed=False,
                        scores=[],
                        selected_skill=None,
                        failures=[MISSING_GOLDEN_REASON],
                    )
            for item in task.files:
                rel = str(item.src).replace("\\", "/").lstrip("/")
                if rel.startswith("evals/goldens/"):
                    continue
                src = resolve_input_file(
                    item.src,
                    skill_root=skill_root,
                    root=root,
                    suite_dir=suite_dir,
                )
                if src is None or not src.is_file():
                    raise SuiteError(
                        f"Couldn't find {item.src} (listed as an input file for {task.id}).",
                        hint="Add the file under evals/fixtures/, or remove it from this check.",
                    )
                copies.append((src, item.dest))
            staged = skills if task.expect_skill is not None else []
            prepare_workspace(sandbox.workspace, staged, copies)
            _seed_skill_selection(sandbox.workspace, task.expect_skill)
            with span("eval.harness", harness.name):
                try:
                    result: HarnessResult = harness.run(sandbox, task.prompt, skills, timeout)
                except CheckAborted as exc:
                    ended = True
                    return _skipped_report(
                        task, KILL_FAILURE if exc.reason == KILL else SKIP_FAILURE
                    )
            if control is not None and control.kill_requested:
                ended = True
                return _skipped_report(task, KILL_FAILURE)
            if control is not None and control.skip_requested:
                ended = True
                return _skipped_report(task, SKIP_FAILURE)
            task_usage: dict[str, Any] | None
            if control is not None:
                if result.usage is not None:
                    control.note_usage(result.usage)
                task_usage = control.usage_dict()
            elif result.usage is not None and result.usage.known:
                task_usage = result.usage.to_dict()
            else:
                task_usage = None
            artifacts = RunArtifacts(
                workspace=sandbox.workspace,
                trigger=result.trigger,
                stdout=result.stdout,
                stderr=result.stderr,
            )
            with span("eval.score", task.id):
                scores = score_task(task, artifacts, skills=skills)
            spans = getattr(result, "spans", None) or _spans_from_transcript(result.transcript)
            from skillgate_ai.metrics import count_path_steps, evaluate_task_metrics

            steps, errors, had_path = count_path_steps(spans, result.transcript)
            det_passed = all(s.passed for s in scores)
            det_failures = [s.headline or s.detail for s in scores if not s.passed]
            if task.expect_skill is None:
                judged = (
                    _no_trigger_skipped_judge(judge)
                    if is_live_harness(harness.name)
                    else None
                )
                passed, failures = det_passed, det_failures
            elif is_live_harness(harness.name):
                judged, mismatch, golden_payload, actual_payload = _run_outcome_judge(
                    task,
                    artifacts,
                    result,
                    scores,
                    harness.name,
                    skill_root=skill_root,
                    path={"steps": steps, "errors": errors, "had_path": had_path},
                    judge=judge,
                )
                passed, failures, judged = _live_verdict(
                    judged,
                    task.expect_skill,
                    det_passed=det_passed,
                    det_failures=det_failures,
                    mismatch=mismatch,
                )
                judged = _maybe_explain_fail(
                    judge,
                    passed,
                    failures,
                    judged,
                    check=task.prompt,
                    transcript_tail=result.transcript,
                    expected_output=_why_expected_output(
                        task,
                        golden_payload,
                        skill_name=skills[0].name if skills else None,
                    ),
                    actual_output=actual_payload,
                )
            else:
                judged = None
                passed, failures = det_passed, det_failures
            primary = skills[0] if skills else None
            advice = (
                advise_task(
                    task,
                    scores,
                    primary,
                    result.trigger.selected_skill,
                    reference=reference,
                    sibling_prompts=sibling_prompts,
                    returncode=result.returncode,
                    stderr=result.stderr or "",
                )
                if primary
                else None
            )
            breadcrumb_task(
                "end",
                task.id,
                passed=passed,
                returncode=result.returncode,
            )
            ended = True
            metrics = evaluate_task_metrics(
                task_usage,
                spans,
                result.transcript,
                getattr(task, "budgets", None),
            )
            return TaskReport(
                task_id=task.id,
                prompt=task.prompt,
                expect_skill=task.expect_skill,
                passed=passed,
                scores=scores,
                selected_skill=result.trigger.selected_skill,
                failures=failures,
                transcript=result.transcript,
                spans=spans,
                stderr=result.stderr,
                returncode=result.returncode,
                files=[{"src": item.src, "dest": item.dest} for item in task.files],
                advice=advice,
                usage=task_usage,
                judge=judged,
                metrics=metrics,
            )
    finally:
        if control is not None:
            sandbox.output_sink = None
            control.end_task()
        if not ended:
            breadcrumb_task("end", task.id, passed=False)


def _skipped_report(task: TaskSpec, reason: str) -> TaskReport:
    from skillgate_ai.metrics import evaluate_task_metrics

    return TaskReport(
        task_id=task.id,
        prompt=task.prompt,
        expect_skill=task.expect_skill,
        passed=False,
        scores=[],
        selected_skill=None,
        failures=[reason],
        skipped=True,
        metrics=evaluate_task_metrics(None, None, "", getattr(task, "budgets", None)),
    )


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


def _spans_from_transcript(transcript: str) -> list[dict[str, Any]] | None:
    from skillgate_ai.spans import spans_from_jsonl

    spans = spans_from_jsonl(transcript or "")
    return spans or None


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
                )
            )
            continue
        is_running = (
            (force_running_id is not None and task.id == force_running_id)
            or (force_running_id is None and index == completed_count)
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
                )
            )
        else:
            tasks.append(TaskProgress(task_id=task.id, prompt=task.prompt, status="queued"))
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
