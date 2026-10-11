"""Load and pin pack checks. Generate never starts a run."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from skillgate_ai.api_payloads import fail, skill_payload, state_of
from skillgate_ai.case_pack import (
    CASES_REL,
    PIN_NEEDS_EXPECTED_HINT,
    checks_from_pack,
    dataset_view,
    expected_without_target_warning,
    load_case_pack,
    pack_judge_dict,
    pin_case_ids,
    pin_checks,
    save_pack_judge,
)
from skillgate_ai.catalog import find_skill
from skillgate_ai.errors import SuiteError
from skillgate_ai.fixture_bind import apply_inherit, expand_from_folder


def register_eval_routes(app: FastAPI) -> None:
    @app.post("/api/evals/generate")
    async def generate(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        yaml_text = str(body.get("yaml") or "").strip()
        pack = load_case_pack(skill_path)
        if yaml_text:
            import yaml as yaml_mod

            from skillgate_ai.case_pack import CasePack, save_case_pack

            raw = yaml_mod.safe_load(yaml_text) or {}
            pack = CasePack.model_validate(raw)
            save_case_pack(skill_path, pack)
        checks: list[dict[str, Any]] = []
        source = "empty"
        note = "Add checks, then press Run. Nothing runs until you do."
        if pack is not None:
            checks = checks_from_pack(pack, include_drafts=True)
            source = "pack"
            note = "These checks are saved with this skill. Edit them, then press Run."
        yaml_out = ""
        cases_file = skill_path / CASES_REL
        if cases_file.is_file():
            yaml_out = cases_file.read_text(encoding="utf-8")
        skill = skill_payload(state, skill_path)
        return {
            "skill": skill,
            "checks": checks,
            "yaml": yaml_out,
            "note": note,
            "source": source,
            "warning": None,
            "fixture_defaults": skill.get("fixture_defaults") or [],
            "pack_judge": pack_judge_dict(pack),
        }

    @app.post("/api/evals/pin")
    async def pin(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        checks = body.get("checks")
        case_ids = body.get("case_ids")
        warnings: list[str] = []
        try:
            if isinstance(checks, list) and checks:
                for raw in checks:
                    if not isinstance(raw, dict):
                        continue
                    warn = expected_without_target_warning(
                        contains=str(raw.get("contains") or raw.get("expected") or ""),
                        output_path=str(raw.get("output_path") or ""),
                        golden_path=str(raw.get("golden_path") or ""),
                        should_trigger=bool(raw.get("should_trigger", True)),
                    )
                    if warn and warn not in warnings:
                        warnings.append(warn)
                pack = pin_checks(skill_path, [dict(item) for item in checks])
            elif isinstance(case_ids, list) and case_ids:
                pack = pin_case_ids(skill_path, [str(item) for item in case_ids])
            else:
                fail(400, "Pin needs checks or case ids.")
            if isinstance(body.get("pack_judge"), dict) or body.get("pack_judge") is None:
                if "pack_judge" in body:
                    pack = save_pack_judge(skill_path, body.get("pack_judge"))
        except ValueError as exc:
            fail(400, str(exc), hint=PIN_NEEDS_EXPECTED_HINT)
        except SuiteError as exc:
            fail(400, exc.message, hint=exc.hint)
        yaml_out = (
            (skill_path / CASES_REL).read_text(encoding="utf-8")
            if (skill_path / CASES_REL).is_file()
            else ""
        )
        return {
            "pack": pack.model_dump() if hasattr(pack, "model_dump") else pack,
            "fingerprint": None,
            "checks": checks_from_pack(pack, include_drafts=True),
            "yaml": yaml_out,
            "skill": skill_payload(state, skill_path),
            "pack_judge": pack_judge_dict(pack),
            "warnings": warnings,
        }

    @app.get("/api/evals/dataset")
    def dataset(skill: str, request: Request) -> dict[str, Any]:
        path = find_skill(state_of(request).root, skill)
        view = dataset_view(path)
        return view or {"skill": path.name, "cases": []}

    @app.post("/api/evals/fixture-bind")
    async def fixture_bind(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        checks = [dict(item) for item in (body.get("checks") or [])]
        inherit = bool(body.get("inherit", True))
        glob_pat = body.get("glob")
        action = str(body.get("action") or "inherit")
        if action == "expand":
            bound = expand_from_folder(skill_path, checks, glob_pat=glob_pat)
        else:
            bound = apply_inherit(skill_path, checks, inherit=inherit, glob_pat=glob_pat)
        skill = skill_payload(state, skill_path)
        return {
            "skill": skill,
            "checks": bound,
            "fixture_defaults": skill.get("fixture_defaults") or [],
            "inherit": inherit,
            "glob": glob_pat,
        }
