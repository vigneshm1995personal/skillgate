#!/usr/bin/env python3
"""Inject _run_task helpers into engine/task.py (split-giant-files step 5)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "src/skillgate_ai/engine/task.py"

HELPERS = '''
def _missing_golden_report(task: TaskSpec, skill_root: Path | None) -> TaskReport | None:
    from skillgate_ai.case_pack import MISSING_GOLDEN_REASON, task_missing_golden

    if skill_root is None or not task_missing_golden(skill_root, task.id):
        return None
    return TaskReport(
        task_id=task.id,
        prompt=task.prompt,
        expect_skill=task.expect_skill,
        passed=False,
        scores=[],
        selected_skill=None,
        failures=[MISSING_GOLDEN_REASON],
    )


def _stage_workspace(
    task: TaskSpec,
    skills: list[Skill],
    harness: Harness,
    sandbox: Sandbox,
    *,
    root: Path,
    suite_dir: Path,
    skill_root: Path | None,
) -> tuple[list[tuple[Path, str]], Any]:
    copies: list[tuple[Path, str]] = []
    for item in task.files:
        rel = str(item.src).replace(chr(92), "/").lstrip("/")
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
    from skillgate_ai.harness import claude_native_skills_enabled

    prepare_workspace(
        sandbox.workspace,
        staged,
        copies,
        stage_claude_native=harness.name == "claude" and claude_native_skills_enabled(),
    )
    if task.trigger_mode:
        mode = sandbox.workspace / ".skillgate" / "mode"
        mode.parent.mkdir(parents=True, exist_ok=True)
        mode.write_text("trigger" + chr(10), encoding="utf-8")
        selected = sandbox.workspace / ".skillgate" / "selected.json"
        if selected.is_file():
            selected.unlink()
    else:
        _seed_skill_selection(sandbox.workspace, task.expect_skill)
    from skillgate_ai.workspace_outputs import snapshot_workspace

    file_baseline = snapshot_workspace(sandbox.workspace)
    return copies, file_baseline


def _raise_if_run_blocked(result: HarnessResult, *, timeout: int) -> HarnessResult:
    run_block_msg = cannot_run_message(
        result.stdout or "", result.stderr or "", result.transcript or ""
    )
    if run_block_msg:
        hint = (
            "Wait until the agent quota resets, then retry."
            if usage_limit_message(
                result.stdout or "", result.stderr or "", result.transcript or ""
            )
            else "Pick an available model, then retry."
        )
        raise HarnessError(
            run_block_msg,
            hint=hint,
            exit_code=2,
        )
    return result


def _task_usage(control: RunControl | None, result: HarnessResult) -> dict[str, Any] | None:
    if control is not None:
        if result.usage is not None:
            control.note_usage(result.usage)
        return control.usage_dict()
    if result.usage is not None and result.usage.known:
        return result.usage.to_dict()
    return None


def _judge_task(
    task: TaskSpec,
    *,
    artifacts: RunArtifacts,
    result: HarnessResult,
    scores: list[Score],
    skills: list[Skill],
    harness: Harness,
    judge: Judge | None,
    skill_root: Path | None,
    spans: Any,
    steps: Any,
    errors: Any,
    had_path: Any,
    file_baseline: Any,
) -> tuple[bool | None, list[str], Any, bool]:
    det_passed = all(s.passed for s in scores)
    det_failures = [s.headline or s.detail for s in scores if not s.passed]
    trigger_passed = all(s.passed for s in scores if s.scorer == "skill_trigger")
    review = False
    passed: bool | None
    if task.expect_skill is None:
        judged = _no_trigger_skipped_judge(judge) if is_live_harness(harness.name) else None
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
            spans=spans,
            skill_instructions=skills[0].body if skills else None,
            file_baseline=file_baseline,
        )
        if isinstance(judged, dict):
            judged = stabilize_adherence_review(judged, scores)
        passed, failures, judged = _live_verdict(
            judged,
            task.expect_skill,
            det_passed=det_passed,
            det_failures=det_failures,
            mismatch=mismatch,
            trigger_passed=trigger_passed,
        )
        review = bool(passed) and bool(isinstance(judged, dict) and judged.get("review"))
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
    return passed, failures, judged, review


def _combined_usage(
    task_usage: dict[str, Any] | None,
    judged: Any,
    result: HarnessResult,
    run_config: dict[str, Any] | None,
) -> dict[str, Any] | None:
    from skillgate_ai.usage import combine_task_usage

    cfg_model = (run_config or {}).get("model") if isinstance(run_config, dict) else None
    judge_block = (run_config or {}).get("judge") if isinstance(run_config, dict) else None
    judge_model = (
        str(judge_block.get("model")).strip()
        if isinstance(judge_block, dict) and judge_block.get("model")
        else None
    )
    from skillgate_ai.harness import AUTH_CLI_LOGIN

    used_model = (result.model or "").strip() or None
    agent_model = used_model or (str(cfg_model).strip() if cfg_model else None)
    return combine_task_usage(
        task_usage,
        judged,
        agent_model=agent_model,
        judge_model=judge_model,
        agent_subscription=getattr(result, "auth_mode", None) == AUTH_CLI_LOGIN,
    )


def _task_advice(
    task: TaskSpec,
    scores: list[Score],
    skills: list[Skill],
    result: HarnessResult,
    *,
    reference: Skill | None,
    sibling_prompts: list[str] | None,
    judged: Any,
) -> FixAdvice | None:
    primary = skills[0] if skills else None
    if not primary:
        return None
    return advise_task(
        task,
        scores,
        primary,
        result.trigger.selected_skill,
        reference=reference,
        sibling_prompts=sibling_prompts,
        returncode=result.returncode,
        stderr=result.stderr or "",
        judge=judged,
    )


'''

NEW_RUN_TASK = '''
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
    run_config: dict[str, Any] | None = None,
) -> TaskReport:
    timeout = task_timeout_sec(task, spec, timeout_override=timeout_override)
    if control is not None:
        sandbox.output_sink = control
        control.begin_task(task.id, task.prompt)
    breadcrumb_task("start", task.id, timeout_sec=timeout)
    ended = False
    try:
        with span("eval.task", task.id, expect_skill=task.expect_skill or ""):
            skill_root = skills[0].path if skills else None
            missing = _missing_golden_report(task, skill_root) if skill_root is not None else None
            if missing is not None:
                ended = True
                return missing
            _, file_baseline = _stage_workspace(
                task,
                skills,
                harness,
                sandbox,
                root=root,
                suite_dir=suite_dir,
                skill_root=skill_root,
            )
            with span("eval.harness", harness.name):
                try:
                    result: HarnessResult = harness.run(sandbox, task.prompt, skills, timeout)
                except CheckAborted as exc:
                    ended = True
                    return _skipped_report(
                        task, KILL_FAILURE if exc.reason == KILL else SKIP_FAILURE
                    )
                except Exception as exc:
                    blocked = timeout_harness_error(exc, timeout_sec=timeout)
                    if blocked is not None:
                        raise blocked from None
                    raise
            _raise_if_run_blocked(result, timeout=timeout)
            if control is not None and control.kill_requested:
                ended = True
                return _skipped_report(task, KILL_FAILURE)
            if control is not None and control.skip_requested:
                ended = True
                return _skipped_report(task, SKIP_FAILURE)
            from skillgate_ai.workspace_outputs import persist_harness_answer

            persist_harness_answer(sandbox.workspace, result.stdout or "")
            task_usage = _task_usage(control, result)
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
            passed, failures, judged, review = _judge_task(
                task,
                artifacts=artifacts,
                result=result,
                scores=scores,
                skills=skills,
                harness=harness,
                judge=judge,
                skill_root=skill_root,
                spans=spans,
                steps=steps,
                errors=errors,
                had_path=had_path,
                file_baseline=file_baseline,
            )
            task_usage = _combined_usage(task_usage, judged, result, run_config)
            advice = _task_advice(
                task, scores, skills, result, reference=reference, sibling_prompts=sibling_prompts, judged=judged
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
            from skillgate_ai.workspace_outputs import collect_workspace_outputs

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
                outputs=collect_workspace_outputs(task, sandbox.workspace, baseline=file_baseline),
                advice=advice,
                usage=task_usage,
                judge=judged,
                metrics=metrics,
                model=result.model,
                review=review,
            )
    finally:
        if control is not None:
            sandbox.output_sink = None
            control.end_task()
        if not ended:
            breadcrumb_task("end", task.id, passed=False)


'''


def main() -> None:
    text = TASK.read_text(encoding="utf-8")
    start = text.index("def _run_task(")
    end = text.index("\ndef _skipped_report(")
    text = text[:start] + HELPERS + NEW_RUN_TASK + text[end + 1 :]
  # strip duplicate future import
    text = text.replace(
        'from __future__ import annotations\n\nfrom __future__ import annotations\n',
        "from __future__ import annotations\n\n",
    )
    TASK.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()