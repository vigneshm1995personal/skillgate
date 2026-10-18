"""Judge prompt for one check. The CLI and the UI both print this text."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from fastapi import Request

from skillgate_ai.errors import SkillGateError
from skillgate_ai.judge_spec import (
    JudgeSpec,
    builtin_spec,
    parse_extra_question,
    resolve_judge_spec,
    spec_decisions_questions,
)


def format_decisions_question(question: Mapping[str, Any]) -> str:
    """Plain text of one decisions question, using the payload strings as sent."""
    lines: list[str] = []
    instructions = str(question.get("instructions") or "").strip()
    if instructions:
        lines.append(instructions)
    choices = question.get("choices")
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, Mapping):
                continue
            value = str(choice.get("value") or "").strip()
            description = str(choice.get("description") or "").strip()
            if value and description:
                lines.append(f"{value}: {description}")
            elif value:
                lines.append(value)
            elif description:
                lines.append(description)
    levels = question.get("levels")
    if isinstance(levels, list):
        for level in levels:
            if isinstance(level, Mapping):
                label = str(level.get("label") or "").strip()
            else:
                label = str(level or "").strip()
            if label:
                lines.append(label)
    return "\n".join(lines)


def list_check_rows(pack: Path | None = None) -> list[dict[str, Any]]:
    spec = _spec_for_pack(pack)
    payloads = {
        str(row.get("name")): row
        for row in spec_decisions_questions(spec, include_path=True)
        if isinstance(row, Mapping)
    }
    rows: list[dict[str, Any]] = []
    for question in spec.questions:
        payload = payloads.get(question.id)
        if payload is None:
            continue
        rows.append(
            {
                "id": question.id,
                "label": question.label,
                "builtin": question.builtin,
                "prompt": format_decisions_question(payload),
            }
        )
    return rows


def prompt_for_id(check_id: str, *, pack: Path | None = None) -> dict[str, Any]:
    wanted = (check_id or "").strip()
    for row in list_check_rows(pack):
        if row["id"] == wanted:
            return row
    raise SkillGateError(f"No check named {wanted}.", exit_code=2)


def preview_question(raw: Mapping[str, Any]) -> dict[str, Any]:
    question = parse_extra_question(raw)
    return {
        "id": question.id,
        "label": question.label,
        "builtin": False,
        "prompt": format_decisions_question(question.to_decisions()),
    }


def _spec_for_pack(pack: Path | None) -> JudgeSpec:
    if pack is None:
        return builtin_spec()
    from skillgate_ai.case_pack import load_case_pack, pack_judge_dict

    loaded = load_case_pack(pack)
    return resolve_judge_spec(pack=pack_judge_dict(loaded))


def register_check_routes(app: Any) -> None:
    from skillgate_ai.api_payloads import fail, state_of
    from skillgate_ai.catalog import find_skill

    def _pack(request: Request, skill: str | None) -> Path | None:
        text = (skill or "").strip()
        if not text:
            return None
        return find_skill(state_of(request).root, text)

    @app.post("/api/checks/preview")
    async def preview_check(request: Request) -> dict[str, Any]:
        body = await request.json()
        raw = body.get("question") if isinstance(body, dict) else None
        if not isinstance(raw, dict):
            fail(400, "Pass the check to preview.")
        try:
            return preview_question(raw)
        except SkillGateError as exc:
            fail(400, exc.message, hint=exc.hint)

    @app.get("/api/checks")
    def list_checks(request: Request, skill: str | None = None) -> dict[str, Any]:
        return {"checks": list_check_rows(_pack(request, skill))}

    @app.get("/api/checks/{check_id}")
    def show_check(
        request: Request, check_id: str, skill: str | None = None
    ) -> dict[str, Any]:
        try:
            return prompt_for_id(check_id, pack=_pack(request, skill))
        except SkillGateError as exc:
            fail(404, exc.message, hint=exc.hint)

    @app.get("/api/settings/judges")
    def list_decision_judges() -> dict[str, Any]:
        from skillgate_ai.judge_settings import decision_judges

        return {"judges": decision_judges()}
