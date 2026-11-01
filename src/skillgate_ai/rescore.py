"""Re-score a saved run from outputs and spans. Does not call the agent or judge."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from skillgate_ai.errors import SkillGateError
from skillgate_ai.history import load_history
from skillgate_ai.judge_bank import CHECK_CELL_ORDER, SOFT_CELL_ORDER, WHY_SUFFIX
from skillgate_ai.judge_spec import (
    JudgeQuestion,
    JudgeSpec,
    extra_block_failures,
    spec_verdict,
)
from skillgate_ai.span_facts import apply_log_facts


def find_history_run(pack: Path, run_id: str) -> dict[str, Any] | None:
    wanted = str(run_id or "").strip()
    if not wanted:
        return None
    for item in load_history(pack, limit=0):
        if str(item.get("run_id") or "") == wanted:
            return item
    return None


def lookup_history_run(run_id: str, dest: Path) -> dict[str, Any]:
    row = find_history_run(dest, run_id)
    if row is None:
        raise SkillGateError(f"No run named {run_id}.", exit_code=2)
    return row


def rescore_saved_run(pack: Path, row: dict[str, Any]) -> dict[str, Any]:
    """Recompute log/text extras and the wording override from saved outputs."""
    from skillgate_ai.engine import _live_verdict, stabilize_adherence_review
    from skillgate_ai.report import hydrate_report_spans
    from skillgate_ai.wording_facts import attach_wording_questions

    out = deepcopy(row)
    report = out.get("report") if isinstance(out.get("report"), dict) else {}
    report = hydrate_report_spans(dict(report))
    skill_text = _skill_text(pack)
    tasks = [item for item in (report.get("tasks") or []) if isinstance(item, dict)]
    passed_count = 0
    failed_ids: list[str] = []
    for task in tasks:
        spec = _spec_for_task(pack, task)
        spec = attach_wording_questions(spec, skill_text)
        judge = dict(task.get("judge") or {}) if isinstance(task.get("judge"), dict) else {}
        answers = dict(judge.get("answers") or {}) if isinstance(judge.get("answers"), dict) else {}
        outputs = task.get("outputs") if isinstance(task.get("outputs"), list) else []
        spans = task.get("spans") if isinstance(task.get("spans"), list) else []
        merged = apply_log_facts(
            spec,
            answers,
            spans,
            outputs=outputs,
            skill_instructions=skill_text,
        )
        supports_confidence = bool(judge.get("supports_confidence"))
        passed, reasons, warnings = spec_verdict(
            spec, merged, supports_confidence=supports_confidence
        )
        extra_failures = extra_block_failures(spec, merged)
        cells = dict(judge.get("cells") or {}) if isinstance(judge.get("cells"), dict) else {}
        _stamp_extra_cells(cells, merged, spec)
        judged = {
            **judge,
            "answers": merged,
            "cells": cells,
            "reasons": reasons,
            "warnings": warnings,
            "extra_failures": extra_failures,
            "passed": passed,
            "questions": {
                **(judge.get("questions") if isinstance(judge.get("questions"), dict) else {}),
                **{q.id: {"instructions": q.ask, "type": q.type} for q in spec.extras},
            },
        }
        scores = task.get("scores") if isinstance(task.get("scores"), list) else []
        judged = stabilize_adherence_review(judged, scores)
        det_passed, det_failures, trigger_passed = _score_bits(scores)
        gate, failures, stamped = _live_verdict(
            judged,
            task.get("expect_skill"),
            det_passed=det_passed,
            det_failures=det_failures,
            trigger_passed=trigger_passed,
        )
        task["judge"] = stamped if stamped is not None else judged
        task["passed"] = gate
        task["failures"] = failures
        _restamp_why(task, skill_text)
        _finish_task(task, gate)
        if gate is True:
            passed_count += 1
        elif gate is False:
            failed_ids.append(str(task.get("id") or task.get("task_id") or ""))
    report["tasks"] = tasks
    report["passed_count"] = passed_count
    report["task_count"] = len(tasks)
    report["failed_task_ids"] = [item for item in failed_ids if item]
    if any(task.get("passed") is False for task in tasks):
        report["passed"] = False
        report["gate"] = "red"
        out["passed"] = False
        out["gate"] = "red"
    elif tasks and all(task.get("passed") is True for task in tasks):
        review = any(
            task.get("review") or (isinstance(task.get("judge"), dict) and task["judge"].get("review"))
            for task in tasks
        )
        warning = any(str(task.get("status") or "") == "warning" for task in tasks)
        report["passed"] = True
        if review:
            report["gate"] = "needs review"
        elif warning:
            report["gate"] = "warning"
        else:
            report["gate"] = "green"
        out["passed"] = True
        out["gate"] = report["gate"]
    out.pop("status", None)
    out["report"] = report
    return out


def _skill_text(pack: Path) -> str | None:
    skill = pack / "SKILL.md"
    if not skill.is_file():
        return None
    text = skill.read_text(encoding="utf-8")
    return text if text.strip() else None


def _spec_for_task(pack: Path, task: dict[str, Any]) -> JudgeSpec:
    from skillgate_ai.case_pack import case_for_task, load_case_pack
    from skillgate_ai.engine import _resolve_task_spec
    from skillgate_ai.judge_spec import builtin_questions

    spec: JudgeSpec | None = None
    try:
        loaded = load_case_pack(pack)
        spec = _resolve_task_spec(
            pack, loaded, case_for_task(loaded, str(task.get("id") or ""))
        )
    except (OSError, SkillGateError):
        spec = None
    if spec is None:
        spec = JudgeSpec(questions=tuple(builtin_questions()))
    judge = task.get("judge") if isinstance(task.get("judge"), dict) else {}
    questions = judge.get("questions") if isinstance(judge.get("questions"), dict) else {}
    known = {q.id for q in spec.questions}
    extra: list[JudgeQuestion] = []
    for qid, blob in questions.items():
        name = str(qid)
        if (
            name in known
            or name in CHECK_CELL_ORDER
            or name in SOFT_CELL_ORDER
            or name.endswith(WHY_SUFFIX)
        ):
            continue
        row = blob if isinstance(blob, dict) else {}
        extra.append(
            JudgeQuestion(
                id=name,
                type=str(row.get("type") or "predicate"),
                ask=str(row.get("instructions") or row.get("ask") or name),
            )
        )
    if extra:
        spec = spec.with_questions([*spec.questions, *extra])
    return spec


def _stamp_extra_cells(
    cells: dict[str, Any],
    merged: dict[str, Any],
    spec: JudgeSpec,
) -> None:
    from skillgate_ai.judge_bank import GUARD_REFUSED_RETRY_NOTE

    for question in spec.extras:
        fact = merged.get(question.id)
        if not isinstance(fact, dict):
            continue
        cell = dict(cells.get(question.id) or {})
        cell["label"] = question.ask
        for key in ("probability", "source", "warning", "reason", "honest_negation"):
            if key in fact:
                cell[key] = fact[key]
        probability = fact.get("probability")
        if isinstance(probability, (int, float)) and not isinstance(probability, bool):
            yes = float(probability) >= 0.8
            cell["probability"] = float(probability)
            cell["choice"] = "Yes" if yes else "No"
            cell["passed"] = yes
            merged[question.id] = {**fact, "choice": cell["choice"], "passed": yes}
        note = str(fact.get("warning") or cell.get("warning") or "").strip()
        if note:
            cell["warning"] = note
            if note == GUARD_REFUSED_RETRY_NOTE:
                cell["passed"] = True
        cells[question.id] = cell


def _restamp_why(task: dict[str, Any], skill_text: str | None) -> None:
    from skillgate_ai.judge_bank import CHECK_CELL_LABELS, CHECK_CELL_ORDER
    from skillgate_ai.judge_context import apply_why_reasons, with_run_reason_questions
    from skillgate_ai.span_facts import _parse_calls_log, _reply_text

    judge = task.get("judge") if isinstance(task.get("judge"), dict) else None
    if not isinstance(judge, dict):
        return
    cells = judge.get("cells") if isinstance(judge.get("cells"), dict) else {}
    answers = judge.get("answers") if isinstance(judge.get("answers"), dict) else {}
    outputs = task.get("outputs") if isinstance(task.get("outputs"), list) else []
    reply = _reply_text(outputs)
    calls = _parse_calls_log(outputs)
    argv0 = []
    for row in calls:
        argv = row.get("argv") if isinstance(row, dict) else None
        if isinstance(argv, list) and argv:
            argv0.append({"argv": argv})
    state = {
        "actual_output": {"body": reply},
        "expected_outcome": str(task.get("prompt") or task.get("scenario") or ""),
        "skill_instructions": skill_text or "",
        "agent_trajectory": {"commands": argv0},
    }
    questions = with_run_reason_questions(
        [
            {
                "type": "choice",
                "name": name,
                "instructions": CHECK_CELL_LABELS[name],
            }
            for name in CHECK_CELL_ORDER
        ],
        state,
    )
    apply_why_reasons(cells, answers, questions)
    stored = judge.get("questions") if isinstance(judge.get("questions"), dict) else {}
    for item in questions:
        name = str(item.get("name") or "")
        if name.endswith("_why"):
            stored[name] = {
                "instructions": item.get("instructions"),
                "type": "choice",
                "choices": item.get("choices"),
            }
    judge["questions"] = stored
    judge["cells"] = cells
    judge["answers"] = answers


def _finish_task(task: dict[str, Any], gate: bool) -> None:
    from skillgate_ai.judge_bank import GUARD_REFUSED_RETRY_NOTE, UNSURE_REVIEW
    from skillgate_ai.run_details import hydrate_task

    judge = task.get("judge") if isinstance(task.get("judge"), dict) else {}
    warnings = [
        str(item).strip()
        for item in (judge.get("warnings") or [])
        if str(item).strip()
    ]
    review = bool(task.get("review") or judge.get("review"))
    if gate is True:
        warnings = [item for item in warnings if item != UNSURE_REVIEW]
        if isinstance(judge, dict):
            judge["warnings"] = warnings
            judge["review"] = False
        task["review"] = False
        review = False
        if GUARD_REFUSED_RETRY_NOTE in warnings:
            task["status"] = "warning"
        else:
            task["status"] = "pass"
        task["happened"] = (
            GUARD_REFUSED_RETRY_NOTE
            if GUARD_REFUSED_RETRY_NOTE in warnings
            else ""
        )
    elif gate is False:
        warnings = [item for item in warnings if item != UNSURE_REVIEW]
        if isinstance(judge, dict):
            judge["warnings"] = warnings
        task["status"] = "fail"
        task["review"] = False
    elif review:
        task["status"] = "unsure"
    task["judge"] = judge
    hydrate_task(task)


def _score_bits(scores: list[Any]) -> tuple[bool, list[str], bool]:
    det_passed = True
    det_failures: list[str] = []
    trigger_passed = True
    saw_trigger = False
    for item in scores:
        if isinstance(item, dict):
            passed = item.get("passed")
            scorer = str(item.get("scorer") or "")
            detail = str(item.get("headline") or item.get("detail") or "")
        else:
            passed = getattr(item, "passed", None)
            scorer = str(getattr(item, "scorer", "") or "")
            detail = str(getattr(item, "headline", "") or getattr(item, "detail", "") or "")
        if passed is False:
            det_passed = False
            if detail:
                det_failures.append(detail)
        if scorer == "skill_trigger":
            saw_trigger = True
            if passed is False:
                trigger_passed = False
    if not saw_trigger:
        trigger_passed = True
    return det_passed, det_failures, trigger_passed
