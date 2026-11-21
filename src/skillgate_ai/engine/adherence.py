"""Run an eval suite through a harness and score every task."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from skillgate_ai.scorers import Score


def _extras_all_passed(judged: Mapping[str, Any]) -> bool:
    """True when extra checks exist and none of them failed."""
    from skillgate_ai.judge_bank import CHECK_CELL_ORDER, SOFT_CELL_ORDER

    failures = judged.get("extra_failures")
    if isinstance(failures, list) and any(str(item).strip() for item in failures):
        return False
    reserved = set(CHECK_CELL_ORDER) | set(SOFT_CELL_ORDER)
    cells = judged.get("cells") if isinstance(judged.get("cells"), Mapping) else {}
    answers = judged.get("answers") if isinstance(judged.get("answers"), Mapping) else {}
    questions = judged.get("questions") if isinstance(judged.get("questions"), Mapping) else {}
    extra_ids = {
        key for blob in (cells, answers, questions) for key in (blob or {}) if key not in reserved
    }
    return bool(extra_ids)


def _extras_from_log(judged: Mapping[str, Any]) -> bool:
    """True when at least one extra check was computed from the log."""
    return _extras_from_source(judged, "log")


def _extras_from_text(judged: Mapping[str, Any]) -> bool:
    """True when at least one extra check was computed from the text."""
    return _extras_from_source(judged, "text")


def _extras_from_source(judged: Mapping[str, Any], source: str) -> bool:
    from skillgate_ai.judge_bank import CHECK_CELL_ORDER, SOFT_CELL_ORDER

    wanted = source.strip().lower()
    reserved = set(CHECK_CELL_ORDER) | set(SOFT_CELL_ORDER)
    cells = judged.get("cells") if isinstance(judged.get("cells"), Mapping) else {}
    answers = judged.get("answers") if isinstance(judged.get("answers"), Mapping) else {}
    for blob in (cells, answers):
        for key, row in (blob or {}).items():
            if key in reserved or not isinstance(row, Mapping):
                continue
            if str(row.get("source") or "").strip().lower() == wanted:
                return True
    return False


def _is_builtin_quality_reason(reason: object) -> bool:
    from skillgate_ai.judge_bank import CHECK_CELL_LABELS

    text = str(reason or "").strip()
    return any(text.startswith(label) for label in CHECK_CELL_LABELS.values())


_NON_WORDING_FAIL = re.compile(
    r"rewrit|verbatim|copy the draft|did not copy|changed the required|"
    r"wrong amount|amount refunded|usd\s*\d|4\.90|49\.00|"
    r"owner[- ]?report|missing step|reply\.txt missing|"
    r"did not write|no owner|skipped the",
    re.IGNORECASE,
)


def _wording_only_builtin_reason(reason: object) -> bool:
    """Judge restated a wording extra. Real quality fails keep their reasons."""
    if not _is_builtin_quality_reason(reason):
        return False
    return not _NON_WORDING_FAIL.search(str(reason or ""))


def stabilize_adherence_review(
    judged: dict[str, Any] | None,
    scores: list[Score] | list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Passing extras and scorers keep a correct hedge from going red.

    The 0.5 floor and the pass mark stay put. This drops the unsure flag on
    builtin cells whose choice is already in PASS_LOCK when every deterministic
    scorer passed. A failing choice at low confidence stays review unless extra
    checks exist, none failed, and the scorers passed. When those extras were
    computed from the log and they all passed, a judge-only builtin quality fail
    is also dropped so an honest hedge does not turn the gate red. A passing
    text check drops a judge fail that only restates that wording rule. A
    rewritten draft, a wrong amount, or a missing step still fails.
    """
    from skillgate_ai.judge_bank import (
        CHECK_CELL_ORDER,
        LOW_CONFIDENCE_WARNING,
        PASS_LOCK,
        canonical_choice,
    )

    if not isinstance(judged, dict):
        return judged
    scorer_ok = True
    for item in scores or []:
        passed = item.passed if isinstance(item, Score) else item.get("passed")
        if passed is False:
            scorer_ok = False
            break
    if not scorer_ok:
        return judged
    cells = judged.get("cells")
    if not isinstance(cells, dict):
        return judged
    extras_ok = _extras_all_passed(judged)
    extras_log = extras_ok and _extras_from_log(judged)
    extras_text = extras_ok and _extras_from_text(judged)
    answers = judged.get("answers") if isinstance(judged.get("answers"), dict) else {}
    next_cells = dict(cells)
    changed = False
    for key in CHECK_CELL_ORDER:
        cell = cells.get(key)
        if not isinstance(cell, dict) or cell.get("status") != "unsure":
            continue
        raw = answers.get(key) if isinstance(answers, dict) else None
        choice = cell.get("choice")
        if not choice and isinstance(raw, dict):
            choice = raw.get("choice")
        canonical = canonical_choice(key, choice)
        allowed = PASS_LOCK.get(key) or frozenset()
        if not extras_ok and (canonical is None or canonical.strip().lower() not in allowed):
            continue
        cleaned = dict(cell)
        cleaned.pop("status", None)
        next_cells[key] = cleaned
        changed = True
    if not changed and not extras_log and not extras_text:
        return judged
    out = dict(judged)
    if changed:
        out["cells"] = next_cells
        review = any(
            isinstance(row, dict) and row.get("status") == "unsure" for row in next_cells.values()
        )
        out["review"] = review
        warnings = [
            str(item).strip()
            for item in (out.get("warnings") or [])
            if str(item).strip() and str(item).strip() != LOW_CONFIDENCE_WARNING
        ]
        if review:
            warnings.append(LOW_CONFIDENCE_WARNING)
        out["warnings"] = warnings
    if extras_log:
        out["passed"] = True
        out["reasons"] = [
            str(item).strip()
            for item in (out.get("reasons") or [])
            if str(item).strip() and not _is_builtin_quality_reason(item)
        ]
        if not changed:
            out["review"] = any(
                isinstance(row, dict) and row.get("status") == "unsure" for row in cells.values()
            )
    elif extras_text:
        kept = [
            str(item).strip()
            for item in (out.get("reasons") or [])
            if str(item).strip() and not _wording_only_builtin_reason(item)
        ]
        out["reasons"] = kept
        if not kept:
            out["passed"] = True
    return out
