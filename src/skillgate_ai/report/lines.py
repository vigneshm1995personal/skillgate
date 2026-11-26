"""Human-readable reports for CLI and GitHub Actions."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from skillgate_ai.engine import TaskReport
from skillgate_ai.judge_bank import UNSURE_REVIEW

_GENERIC_FAILS = frozenset(
    {
        "this check did not pass.",
        "the judge couldn't score this check.",
    }
)


def _task_fail_line(task: TaskReport) -> str:
    judge = task.judge if isinstance(task.judge, dict) else {}
    if isinstance(judge, dict):
        from skillgate_ai.advice import behavior_fail_line, behavior_question_ids

        questions = behavior_question_ids(judge)
        if questions:
            return behavior_fail_line(questions[0])
        extras = judge.get("extra_failures")
        if isinstance(extras, list):
            for item in extras:
                text = str(item).strip()
                if text:
                    return text
        named = _named_builtin_fail(judge)
        if named:
            return named
    why = judge.get("why") if isinstance(judge, dict) else None
    if isinstance(why, str) and why.strip():
        return why.strip()
    for item in task.failures:
        text = str(item).strip()
        if text and text.lower() not in _GENERIC_FAILS:
            return text
    return "This check did not pass."


def _named_builtin_fail(judge: Mapping[str, Any]) -> str | None:
    from skillgate_ai.judge_bank import (
        CHECK_CELL_LABELS,
        PASS_LOCK,
        canonical_choice,
        extract_choice,
    )

    for item in judge.get("reasons") or []:
        text = str(item).strip()
        if not text or text.lower() in _GENERIC_FAILS:
            continue
        if any(text.startswith(label) for label in CHECK_CELL_LABELS.values()):
            return text
    cells = judge.get("cells") if isinstance(judge.get("cells"), dict) else {}
    for key, label in CHECK_CELL_LABELS.items():
        cell = cells.get(key) if isinstance(cells, dict) else None
        if not isinstance(cell, dict):
            continue
        choice = str(cell.get("choice") or extract_choice(cell) or "").strip()
        if not choice:
            continue
        canonical = canonical_choice(key, choice)
        if canonical and canonical.strip().lower() in PASS_LOCK[key]:
            continue
        reason = str(cell.get("reason") or "").strip()
        line = f"{label} {choice}"
        if reason and reason not in line:
            line = f"{line} — {reason}"
        return line
    return None


def _task_happened(task: TaskReport) -> str:
    """Plain What happened line. Never blank."""
    if task.passed is None:
        return "not scored"
    if task.passed:
        warnings = _task_warnings(task)
        if warnings:
            return warnings[0]
        if task.expect_skill is None:
            return "No skill was picked, as expected."
        return "Output matched what was expected."
    return _task_fail_line(task)


def _cell_answer(cell: dict, answer: Any = None) -> str:
    merged = dict(cell)
    if isinstance(answer, dict):
        for key in ("choice", "probability", "score"):
            if merged.get(key) in (None, "") and answer.get(key) is not None:
                merged[key] = answer[key]
        if answer.get("status"):
            merged["status"] = answer.get("status")
    if str(merged.get("status") or "") == "unsure":
        return UNSURE_REVIEW
    choice = str(merged.get("choice") or "").strip()
    if choice:
        return choice
    probability = merged.get("probability")
    if isinstance(probability, (int, float)) and not isinstance(probability, bool):
        return "Yes" if float(probability) >= 0.8 else "No"
    score = merged.get("score")
    if isinstance(score, (int, float)) and not isinstance(score, bool):
        return str(score)
    if isinstance(score, str) and score.strip():
        return score.strip()
    reason = str(merged.get("reason") or "").strip()
    if reason.lower().startswith("not available"):
        return "Not available"
    label = str(merged.get("label") or "").strip()
    if label.lower() in {"path", "how it ran"}:
        return "Not available"
    return reason or "Not available"


def _task_check_answers(task: TaskReport) -> tuple[list[dict[str, str]], str]:
    """Plain expandable answers. OpenAI cells, else what the checks recorded."""
    judge = task.judge if isinstance(task.judge, dict) else {}
    raw = judge.get("cells") if isinstance(judge, dict) else None
    cells: list[dict] = []
    if isinstance(raw, dict):
        cells = [item for item in raw.values() if isinstance(item, dict)]
    elif isinstance(raw, list):
        cells = [item for item in raw if isinstance(item, dict)]
    if cells:
        raw_answers_map = judge.get("answers")
        answers_map: Mapping[str, Any] = (
            raw_answers_map if isinstance(raw_answers_map, dict) else {}
        )
        rows: list[dict[str, str]] = []
        if isinstance(raw, dict):
            pairs = ((str(key), cell) for key, cell in raw.items() if isinstance(cell, dict))
        else:
            pairs = ((str(cell.get("label") or ""), cell) for cell in cells)
        for key, cell in pairs:
            row = {
                "label": str(cell.get("label") or "").strip() or "Check",
                "answer": _cell_answer(cell, answers_map.get(key)),
            }
            source = _check_source(cell, answers_map.get(key), key)
            if source:
                row["source"] = source
                label = _source_label(source)
                if label:
                    row["source_label"] = label
            rows.append(row)
        return rows, "openai"
    rows = []
    for score in task.scores:
        title = (score.headline or score.detail or "Check").strip()
        mark = "Yes" if score.passed else "No"
        extra = ""
        if score.detail and score.detail != title:
            extra = f" — {score.detail}"
        rows.append({"label": title, "answer": f"{mark}{extra}"})
    return rows, "builtin"


def _source_label(source: str | None) -> str | None:
    raw = str(source or "").strip().lower()
    if raw in {"text", "log/text"}:
        return "from the log/text"
    if raw == "log":
        return "from the log"
    if raw == "judge":
        return "from the judge"
    return None


def _check_source(cell: Mapping[str, Any] | None, answer: Any, key: str) -> str | None:
    from skillgate_ai.judge_bank import CHECK_CELL_ORDER, SOFT_CELL_ORDER

    if key in CHECK_CELL_ORDER or key in SOFT_CELL_ORDER:
        return None
    for blob in (cell, answer if isinstance(answer, dict) else None):
        if isinstance(blob, dict):
            raw = str(blob.get("source") or "").strip().lower()
            if raw in {"log", "judge", "text", "log/text"}:
                return raw
    return "judge"


def _extra_source_lines(task: TaskReport) -> list[str]:
    from skillgate_ai.judge_bank import CHECK_CELL_ORDER, SOFT_CELL_ORDER

    judge = task.judge if isinstance(task.judge, dict) else {}
    raw_cells = judge.get("cells")
    cells: Mapping[str, Any] = raw_cells if isinstance(raw_cells, dict) else {}
    raw_answers = judge.get("answers")
    answers: Mapping[str, Any] = raw_answers if isinstance(raw_answers, dict) else {}
    lines: list[str] = []
    for key, cell in cells.items():
        if key in CHECK_CELL_ORDER or key in SOFT_CELL_ORDER:
            continue
        if not isinstance(cell, dict):
            continue
        source = _source_label(_check_source(cell, answers.get(key), key))
        if not source:
            continue
        label = str(cell.get("label") or key).strip()
        choice = _cell_answer(cell, answers.get(key))
        lines.append(f"{label}  {choice}  ({source})")
    return lines


def _task_warnings(task: TaskReport) -> list[str]:
    judge = task.judge if isinstance(task.judge, dict) else {}
    raw = judge.get("warnings") if isinstance(judge, dict) else None
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]
