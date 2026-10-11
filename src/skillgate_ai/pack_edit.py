"""Add custom checks and extra scoring questions to a pack."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from skillgate_ai.case_pack import (
    _slug_id,
    expected_without_target_warning,
    load_case_pack,
    pin_checks,
    save_pack_judge,
)
from skillgate_ai.errors import SuiteError
from skillgate_ai.judge_spec import parse_extra_question, resolve_judge_spec
from skillgate_ai.pack_schema import ExtraQuestion, JudgeBlock


def add_judge_question(
    skill_path: str | Path,
    *,
    ask: str,
    kind: str = "predicate",
    question_id: str | None = None,
    on_fail: str = "block",
):
    root = Path(skill_path).expanduser().resolve()
    pack = load_case_pack(root)
    if pack is None:
        raise SuiteError("This skill has no case pack yet.")
    qid = (question_id or "").strip() or _question_id(ask)
    parsed = parse_extra_question(
        {
            "id": qid,
            "type": kind,
            "ask": ask,
            "on_fail": on_fail,
            "pass_if": {"gte": 0.8} if kind.lower() in {"predicate", "yes/no"} else None,
        }
    )
    extra = ExtraQuestion(
        id=parsed.id,
        type=parsed.type,  # type: ignore[arg-type]
        ask=parsed.ask,
        on_fail=parsed.on_fail,  # type: ignore[arg-type]
        choices=list(parsed.choices) or None,
        levels=list(parsed.levels) or None,
        pass_if=parsed.pass_if,
        include_when=parsed.include_when,
    )
    current = pack.judge or JudgeBlock()
    extras = [*current.extra_questions, extra]
    updated_block = current.model_copy(update={"extra_questions": extras})
    resolve_judge_spec(pack=updated_block.to_sparse_dict())
    return save_pack_judge(root, updated_block.to_sparse_dict())


def add_pack_case(
    skill_path: str | Path,
    *,
    prompt: str,
    case_id: str | None = None,
    expected: str | None = None,
    output_path: str | None = None,
    should_trigger: bool = True,
    files: list[dict[str, Any]] | None = None,
):
    check: dict[str, Any] = {
        "id": case_id or _slug_id(prompt),
        "prompt": prompt,
        "should_trigger": should_trigger,
        "files": files or [],
    }
    if expected:
        check["contains"] = expected
    if output_path:
        check["output_path"] = output_path
    warning = expected_without_target_warning(
        contains=expected,
        output_path=output_path,
        golden_path=None,
        should_trigger=should_trigger,
    )
    return pin_checks(skill_path, [check]), warning


def _question_id(ask: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", ask.strip().lower()).strip("_")[:64]
    return slug or "extra"
