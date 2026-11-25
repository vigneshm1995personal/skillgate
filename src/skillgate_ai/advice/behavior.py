from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from skillgate_ai.advice.model import BEHAVIOR_FAIL_LEAD, TRIGGER_SECONDARY_NOTE, FixAdvice
from skillgate_ai.judge_bank import CHECK_CELL_ORDER, SOFT_CELL_ORDER


def behavior_fail_line(question: str) -> str:
    return BEHAVIOR_FAIL_LEAD.format(question=question)


def behavior_question_ids(judge: dict | None) -> list[str]:
    """Ids (or labels) of extra behavior questions that failed this run."""
    if not isinstance(judge, dict):
        return []
    reserved = set(CHECK_CELL_ORDER) | set(SOFT_CELL_ORDER)
    extras = [
        str(item).strip() for item in (judge.get("extra_failures") or []) if str(item).strip()
    ]
    raw_cells = judge.get("cells")
    cells: Mapping[str, Any] = raw_cells if isinstance(raw_cells, dict) else {}
    raw_questions = judge.get("questions")
    questions: Mapping[str, Any] = raw_questions if isinstance(raw_questions, dict) else {}
    found: list[str] = []

    def add(qid: str) -> None:
        name = str(qid).strip()
        if name and name not in found and name not in reserved:
            found.append(name)

    for text in extras:
        matched = False
        for qid, cell in cells.items():
            if isinstance(cell, dict) and str(cell.get("reason") or "").strip() == text:
                add(str(qid))
                matched = True
                break
        if not matched:
            for qid, meta in questions.items():
                ask = ""
                if isinstance(meta, dict):
                    ask = str(meta.get("instructions") or "").strip()
                if ask and (text == f"{ask} No" or text.startswith(ask)):
                    add(str(qid))
                    matched = True
                    break
        if not matched:
            add(text[:-3].rstrip() if text.endswith(" No") else text)
    return found


def _behavior_fix(question: str, *, skill_unopened: bool) -> FixAdvice:
    why = behavior_fail_line(question)
    if skill_unopened:
        why = f"{why} {TRIGGER_SECONDARY_NOTE}"
    return FixAdvice(
        headline="The agent's behavior failed this check",
        why=why,
        change="Review the run log below.",
        paste="",
        target="body",
    )
