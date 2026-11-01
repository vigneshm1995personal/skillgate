"""One scoring function for live check and rescore. No second verdict path."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from skillgate_ai.errors import SkillGateError
from skillgate_ai.judge_bank import (
    CHECK_CELL_ORDER,
    GUARD_REFUSED_RETRY_NOTE,
    PASS_LOCK,
    SOFT_CELL_ORDER,
    UNSURE_REVIEW,
    WHY_SUFFIX,
    canonical_choice,
    extract_choice,
    extract_reason,
    is_built_reason,
    is_rubric_reason,
)
from skillgate_ai.judge_spec import (
    JudgeQuestion,
    JudgeSpec,
    extra_block_failures,
    spec_verdict,
)
from skillgate_ai.span_facts import apply_log_facts


def score_run(
    *,
    spec: JudgeSpec,
    judged: Mapping[str, Any] | None,
    outputs: Sequence[Any] | None = None,
    spans: Sequence[Any] | None = None,
    scores: Sequence[Any] | None = None,
    skill_text: str | None = None,
    expect_skill: str | None = "",
    mismatch: str | None = None,
) -> dict[str, Any]:
    """Gate a run from judge answers plus outputs/spans. Live check and rescore call this."""
    from skillgate_ai.wording_facts import attach_wording_questions

    spec = attach_wording_questions(spec, skill_text)
    raw = dict(judged) if isinstance(judged, Mapping) else {}
    answers = dict(raw.get("answers") or {}) if isinstance(raw.get("answers"), dict) else {}
    cells = dict(raw.get("cells") or {}) if isinstance(raw.get("cells"), dict) else {}
    merged = apply_log_facts(
        spec,
        answers,
        spans,
        outputs=outputs,
        skill_instructions=skill_text,
    )
    supports_confidence = bool(raw.get("supports_confidence"))
    include_path = True
    passed, reasons, warnings = spec_verdict(
        spec, merged, supports_confidence=supports_confidence, include_path=include_path
    )
    extra_failures = extra_block_failures(spec, merged)
    stamp_extra_cells(cells, merged, spec)
    drop_unsure_on_pass_lock(cells, merged)
    drop_assembled_reasons(cells, merged)
    out = {
        **raw,
        "answers": merged,
        "cells": cells,
        "reasons": reasons,
        "warnings": warnings,
        "extra_failures": extra_failures,
        "passed": passed,
        "questions": {
            **(raw.get("questions") if isinstance(raw.get("questions"), dict) else {}),
            **{q.id: {"instructions": q.ask, "type": q.type} for q in spec.extras},
        },
        "review": False,
    }
    det_passed, det_failures, trigger_passed = score_bits(scores)
    gate, failures = apply_gate(
        out,
        expect_skill=expect_skill,
        det_passed=det_passed,
        det_failures=det_failures,
        trigger_passed=trigger_passed,
        mismatch=mismatch,
    )
    out["passed"] = gate
    out["reasons"] = failures
    strip_unsure(out, gate)
    return out


def apply_gate(
    judged: dict[str, Any],
    *,
    expect_skill: str | None,
    det_passed: bool,
    det_failures: Sequence[str],
    trigger_passed: bool,
    mismatch: str | None = None,
) -> tuple[bool | None, list[str]]:
    """Single gate. Every builtin fail stays red. No wording override."""
    from skillgate_ai.judge_bank import UNUSABLE_ANSWER

    if trigger_passed is False:
        reasons = list(det_failures) or [
            "Did not trigger (description does not match this request)"
        ]
        judged["passed"] = False
        judged["review"] = False
        return False, reasons
    extra = [
        str(item).strip()
        for item in (judged.get("extra_failures") or [])
        if str(item).strip()
    ]
    if expect_skill is None:
        if judged.get("score_no_trigger") and extra:
            judged["passed"] = False
            return False, extra
        return det_passed, list(det_failures)
    if extra:
        judged["passed"] = False
        return False, extra
    if builtin_choice_failed(judged):
        failures = [
            str(item) for item in (judged.get("reasons") or []) if str(item).strip()
        ]
        judged["passed"] = False
        return False, failures or ["Got it right? Incorrect"]
    if judged.get("status") == "error":
        reason = str(judged.get("reason") or "").strip()
        if not reason:
            reasons = judged.get("reasons") or []
            if isinstance(reasons, list) and reasons:
                reason = str(reasons[0]).strip()
        if not reason:
            reason = "Quality was not scored."
        judged["quality_unscored"] = True
        judged["reason"] = reason
        if not det_passed:
            judged["passed"] = False
            return False, list(det_failures)
        if reason == UNUSABLE_ANSWER:
            judged["passed"] = False
            return False, [reason]
        judged["passed"] = None
        return None, [reason]
    if judged.get("status") == "skip" or judged.get("passed") is None:
        return det_passed, list(det_failures)
    passed = bool(judged.get("passed"))
    failures = [str(item) for item in (judged.get("reasons") or []) if str(item).strip()]
    if not passed and not failures:
        failures = list(det_failures) or ["The judge couldn't score this check."]
    if mismatch:
        if mismatch not in failures:
            failures = [mismatch, *failures]
        return False, failures
    judged["passed"] = passed
    return passed, failures


def builtin_choice_failed(judged: Mapping[str, Any]) -> bool:
    """True when any built-in Pass-lock cell failed. No exceptions."""
    cells = judged.get("cells") if isinstance(judged.get("cells"), Mapping) else {}
    answers = judged.get("answers") if isinstance(judged.get("answers"), Mapping) else {}
    for key in CHECK_CELL_ORDER:
        cell = cells.get(key) if isinstance(cells.get(key), Mapping) else {}
        raw = answers.get(key)
        choice = cell.get("choice") if isinstance(cell, Mapping) else None
        if not choice:
            choice = extract_choice(raw)
        canonical = canonical_choice(key, str(choice) if choice else None)
        allowed = PASS_LOCK.get(key) or frozenset()
        if canonical is None:
            continue
        if canonical.strip().lower() not in allowed:
            return True
    return False


def drop_unsure_on_pass_lock(cells: dict[str, Any], answers: Mapping[str, Any]) -> None:
    for key in CHECK_CELL_ORDER:
        cell = cells.get(key)
        if not isinstance(cell, dict) or cell.get("status") != "unsure":
            continue
        raw = answers.get(key) if isinstance(answers, Mapping) else None
        choice = cell.get("choice")
        if not choice and isinstance(raw, dict):
            choice = raw.get("choice")
        canonical = canonical_choice(key, choice)
        allowed = PASS_LOCK.get(key) or frozenset()
        if canonical is None or canonical.strip().lower() not in allowed:
            continue
        cell.pop("status", None)


def drop_assembled_reasons(cells: dict[str, Any], answers: dict[str, Any]) -> None:
    """Keep only a reason the judge wrote. Assembled run-text lines are dropped."""
    for key in (*CHECK_CELL_ORDER, *SOFT_CELL_ORDER):
        cell = cells.get(key) if isinstance(cells.get(key), dict) else None
        blob = answers.get(key) if isinstance(answers.get(key), dict) else None
        choice = None
        if isinstance(cell, dict):
            choice = cell.get("choice")
        if not choice and isinstance(blob, dict):
            choice = extract_choice(blob)
        reason = None
        if isinstance(cell, dict):
            reason = str(cell.get("reason") or "").strip() or None
        if not reason and isinstance(blob, dict):
            reason = extract_reason(blob)
        if not reason or is_built_reason(reason) or is_rubric_reason(key, choice, reason):
            if isinstance(cell, dict):
                cell["reason"] = None
            if (
                isinstance(blob, dict)
                and str(blob.get("reason") or "").strip()
                and (
                    is_built_reason(blob.get("reason"))
                    or is_rubric_reason(key, choice, str(blob.get("reason") or ""))
                )
            ):
                blob.pop("reason", None)
            continue
        if isinstance(cell, dict):
            cell["reason"] = reason


def stamp_extra_cells(
    cells: dict[str, Any],
    merged: dict[str, Any],
    spec: JudgeSpec,
) -> None:
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


def strip_unsure(judged: dict[str, Any], gate: bool | None) -> None:
    if gate is not True and gate is not False:
        return
    warnings = [
        str(item).strip()
        for item in (judged.get("warnings") or [])
        if str(item).strip() and str(item).strip() != UNSURE_REVIEW
    ]
    judged["warnings"] = warnings
    judged["review"] = False
    cells = judged.get("cells") if isinstance(judged.get("cells"), dict) else {}
    for cell in cells.values():
        if isinstance(cell, dict) and cell.get("status") == "unsure":
            cell.pop("status", None)


def finish_task(task: dict[str, Any], gate: bool | None) -> None:
    from skillgate_ai.run_details import hydrate_task

    judge = task.get("judge") if isinstance(task.get("judge"), dict) else {}
    warnings = [
        str(item).strip()
        for item in (judge.get("warnings") or [])
        if str(item).strip()
    ]
    if gate is True:
        warnings = [item for item in warnings if item != UNSURE_REVIEW]
        judge["warnings"] = warnings
        judge["review"] = False
        task["review"] = False
        if GUARD_REFUSED_RETRY_NOTE in warnings:
            task["status"] = "warning"
        else:
            task["status"] = "pass"
        task["happened"] = (
            GUARD_REFUSED_RETRY_NOTE if GUARD_REFUSED_RETRY_NOTE in warnings else ""
        )
    elif gate is False:
        warnings = [item for item in warnings if item != UNSURE_REVIEW]
        judge["warnings"] = warnings
        judge["review"] = False
        task["status"] = "fail"
        task["review"] = False
    elif task.get("review") or judge.get("review"):
        task["status"] = "unsure"
    task["judge"] = judge
    hydrate_task(task)


def score_bits(scores: Sequence[Any] | None) -> tuple[bool, list[str], bool]:
    det_passed = True
    det_failures: list[str] = []
    trigger_passed = True
    saw_trigger = False
    for item in scores or []:
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


def spec_for_task(pack: Any, task: Mapping[str, Any]) -> JudgeSpec:
    from pathlib import Path

    from skillgate_ai.case_pack import case_for_task, load_case_pack
    from skillgate_ai.engine import _resolve_task_spec
    from skillgate_ai.judge_spec import builtin_questions

    root = Path(pack) if pack is not None else None
    spec: JudgeSpec | None = None
    if root is not None:
        try:
            loaded = load_case_pack(root)
            spec = _resolve_task_spec(
                root, loaded, case_for_task(loaded, str(task.get("id") or ""))
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


def verdict_json(judged: Mapping[str, Any] | None) -> dict[str, Any]:
    """Comparable slice: gate, extras, builtin choices, and written reasons."""
    raw = judged if isinstance(judged, Mapping) else {}
    cells = raw.get("cells") if isinstance(raw.get("cells"), Mapping) else {}
    answers = raw.get("answers") if isinstance(raw.get("answers"), Mapping) else {}
    builtins: dict[str, Any] = {}
    for key in CHECK_CELL_ORDER:
        cell = cells.get(key) if isinstance(cells.get(key), Mapping) else {}
        blob = answers.get(key) if isinstance(answers.get(key), Mapping) else {}
        choice = (cell.get("choice") if isinstance(cell, Mapping) else None) or extract_choice(
            blob
        )
        reason = None
        if isinstance(cell, Mapping):
            reason = str(cell.get("reason") or "").strip() or None
        if not reason and isinstance(blob, Mapping):
            reason = extract_reason(blob)
        builtins[key] = {"choice": choice, "reason": reason}
    extras: dict[str, Any] = {}
    for key, row in {**cells, **answers}.items():
        if key in CHECK_CELL_ORDER or key in SOFT_CELL_ORDER or str(key).endswith(WHY_SUFFIX):
            continue
        if not isinstance(row, Mapping):
            continue
        extras[str(key)] = {
            "choice": row.get("choice"),
            "probability": row.get("probability"),
            "passed": row.get("passed"),
            "warning": row.get("warning"),
        }
    warnings = [
        str(item).strip()
        for item in (raw.get("warnings") or [])
        if str(item).strip()
    ]
    return {
        "passed": raw.get("passed"),
        "reasons": [str(item) for item in (raw.get("reasons") or []) if str(item).strip()],
        "warnings": warnings,
        "builtins": builtins,
        "extras": extras,
    }
