"""Run an eval suite through a harness and score every task."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skillgate_ai.harness import (
    HarnessResult,
    is_live_harness,
)
from skillgate_ai.judge import Judge, SkipJudge, judge_stamp
from skillgate_ai.judge_bank import UNUSABLE_ANSWER
from skillgate_ai.output_match import expected_output_mismatch_reason
from skillgate_ai.scorers import RunArtifacts, Score
from skillgate_ai.suite import TaskSpec


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
                from skillgate_ai.judge_context import enrich_output_row

                sniffed = sniff_output_bytes(dest.read_bytes())
                row.update(sniffed)
                row = enrich_output_row(row, dest)
            outputs.append(row)
    return outputs


def _resolve_task_spec(skill_root: Path, pack: Any, case: Any):
    from skillgate_ai.case_pack import pack_judge_dict
    from skillgate_ai.judge_spec import resolve_judge_spec
    from skillgate_ai.paths import project_root
    from skillgate_ai.project_config import load_project_judge

    project = load_project_judge(project_root())
    pack_block = pack_judge_dict(pack) if pack is not None else None
    case_block = None
    if case is not None and getattr(case, "judge", None) is not None:
        case_block = case.judge.to_sparse_dict()
    return resolve_judge_spec(project=project, pack=pack_block, case=case_block)


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
    spans: list[dict[str, Any]] | None = None,
    skill_instructions: str | None = None,
    file_baseline: dict[str, tuple[int, int]] | None = None,
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
    spec = None
    if skill_root is not None:
        from skillgate_ai.case_pack import (
            actual_output_state,
            case_for_task,
            golden_state,
            load_case_pack,
        )

        pack = load_case_pack(skill_root)
        case = case_for_task(pack, task.id)
        spec = _resolve_task_spec(skill_root, pack, case)
        if case is not None and (
            case.golden is not None or (case.output_optional and case.contains)
        ):
            golden_payload = golden_state(
                case.golden,
                skill_root,
                contains=case.contains,
                output_optional=case.output_optional,
            )
            output_path = case.golden.output_path if case.golden is not None else None
            actual_payload = (
                actual_output_state(output_path, artifacts.workspace) if output_path else None
            )
    from skillgate_ai.judge_context import build_agent_trajectory, skill_instructions_text
    from skillgate_ai.workspace_outputs import collect_workspace_outputs

    outputs = collect_workspace_outputs(task, artifacts.workspace, baseline=file_baseline)
    if not outputs:
        outputs = _outcome_judge_outputs(task, artifacts)
    trajectory = build_agent_trajectory(
        spans=spans,
        transcript=result.transcript,
        path=path,
        scores=scores,
        artifacts=outputs,
        command_log=result.stdout or None,
    )
    instructions = skill_instructions_text(skill_root, fallback=skill_instructions)
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
        spec=spec,
        skill_instructions=instructions,
        agent_trajectory=trajectory,
        spans=spans,
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
    questions = {key: {"instructions": CHECK_CELL_LABELS[key]} for key in CHECK_CELL_ORDER}
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
    trigger_passed: bool | None = None,
) -> tuple[bool, list[str], dict[str, Any] | None]:
    """Skip leaves det in charge. Errors fail closed. No-trigger keeps det.
    A completed bool ``passed`` overrides, including a low-confidence Pass.
    A failed skill trigger cannot pass or review. Gate ``passed`` is the
    return value. Cell ``passed`` stays on the judge dict."""
    if trigger_passed is False:
        reasons = list(det_failures) or [
            "Did not trigger (description does not match this request)"
        ]
        if not isinstance(judge, dict):
            return False, reasons, judge
        stamped = {**judge, "passed": False, "review": False}
        return False, reasons, stamped
    if not isinstance(judge, dict):
        return det_passed, det_failures, judge
    warnings = [str(item) for item in (judge.get("warnings") or []) if str(item).strip()]
    stamped = {**judge, "warnings": warnings}
    extra = [str(item).strip() for item in (judge.get("extra_failures") or []) if str(item).strip()]
    if expect_skill is None:
        if judge.get("score_no_trigger") and extra:
            return False, extra, stamped
        return det_passed, det_failures, stamped
    if extra:
        stamped = {**stamped, "passed": False}
        return False, extra, stamped
    if judge.get("status") == "error":
        reason = str(stamped.get("reason") or "").strip()
        if not reason:
            reasons = judge.get("reasons") or []
            if isinstance(reasons, list) and reasons:
                reason = str(reasons[0]).strip()
        if not reason:
            reason = "Quality was not scored."
        unscored = {
            **stamped,
            "passed": None,
            "quality_unscored": True,
            "reason": reason,
        }
        if not det_passed:
            return False, list(det_failures), unscored
        if reason == UNUSABLE_ANSWER:
            return False, [reason], {**unscored, "passed": False}
        return None, [reason], unscored  # type: ignore[return-value]  # tri-state verdict: None = unscored; signature declares bool
    if judge.get("status") == "skip" or judge.get("passed") is None:
        return det_passed, det_failures, judge
    passed = bool(judge.get("passed"))
    failures = [str(item) for item in (judge.get("reasons") or []) if str(item).strip()]
    if not passed and not failures:
        failures = list(det_failures) or ["The judge couldn't score this check."]
    passed, failures = _apply_mismatch(passed, failures, mismatch)
    return passed, failures, stamped


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
    if judged.get("status") == "error" or judged.get("quality_unscored"):
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
