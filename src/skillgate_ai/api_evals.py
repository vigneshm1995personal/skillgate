"""Load and pin pack checks. Generate never starts a run."""

from __future__ import annotations

from typing import Any

from skillgate_ai.extras import UI_FEATURE, MissingExtraError

try:
    from fastapi import Body, FastAPI, File, Form, Request, UploadFile
except ModuleNotFoundError as exc:
    raise MissingExtraError(UI_FEATURE, "ui") from exc

from skillgate_ai.api_models import EvalFixtureBindBody, EvalGenerateBody, EvalPinBody
from skillgate_ai.api_payloads import fail, skill_payload, state_of
from skillgate_ai.case_pack import (
    CASES_REL,
    PIN_NEEDS_EXPECTED_HINT,
    checks_from_pack,
    dataset_view,
    load_case_pack,
    pack_judge_dict,
)
from skillgate_ai.catalog import find_skill
from skillgate_ai.errors import SuiteError
from skillgate_ai.fixture_bind import apply_inherit, expand_from_folder
from skillgate_ai.pack_io import is_pack_file, read_pack_text
from skillgate_ai.paths import require_under


def register_eval_routes(app: FastAPI) -> None:
    @app.post("/api/evals/generate")
    async def generate(request: Request, payload: EvalGenerateBody = Body()) -> dict[str, Any]:
        state = state_of(request)
        skill_path = require_under(state.root, find_skill(state.root, payload.skill))
        yaml_text = str(payload.yaml or "").strip()
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
        has_cases = is_pack_file(skill_path, CASES_REL)
        yaml_out = read_pack_text(skill_path, CASES_REL) if has_cases else ""
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
    async def pin(request: Request, payload: EvalPinBody = Body()) -> dict[str, Any]:
        state = state_of(request)
        skill_path = require_under(state.root, find_skill(state.root, payload.skill))
        checks = payload.checks
        case_ids = payload.case_ids
        dumped = payload.model_dump(exclude_unset=True)
        warnings: list[str] = []
        try:
            from skillgate_ai.pack_edit import apply_pin

            pack, warnings = apply_pin(
                skill_path,
                checks=checks if isinstance(checks, list) else None,
                case_ids=case_ids if isinstance(case_ids, list) else None,
                pack_judge=payload.pack_judge if isinstance(payload.pack_judge, dict) else None,
                has_pack_judge="pack_judge" in dumped,
            )
        except ValueError as exc:
            fail(400, str(exc), hint=PIN_NEEDS_EXPECTED_HINT)
        except SuiteError as exc:
            fail(400, exc.message, hint=exc.hint)
        has_cases = is_pack_file(skill_path, CASES_REL)
        yaml_out = read_pack_text(skill_path, CASES_REL) if has_cases else ""
        return {
            "pack": pack.model_dump() if hasattr(pack, "model_dump") else pack,
            "fingerprint": None,
            "checks": checks_from_pack(pack, include_drafts=True),
            "yaml": yaml_out,
            "skill": skill_payload(state, skill_path),
            "pack_judge": pack_judge_dict(pack),
            "warnings": warnings,
        }

    @app.post("/api/evals/import-dataset")
    async def import_dataset(
        request: Request,
        skill: str = Form(...),
        file: UploadFile = File(...),
        dry_run: bool = Form(False),
        on_conflict: str = Form("fail"),
        confirm: bool = Form(False),
    ) -> dict[str, Any]:
        state = state_of(request)
        skill_path = require_under(state.root, find_skill(state.root, skill))
        conflict = str(on_conflict or "fail").strip().lower()
        if conflict not in {"fail", "skip", "replace"}:
            fail(400, "on_conflict must be fail, skip, or replace.")
        data = await file.read()
        from skillgate_ai.case_import import CaseImportError, apply_case_import, plan_case_import

        try:
            if dry_run or not confirm:
                plan = plan_case_import(
                    skill_path,
                    data,
                    filename=file.filename,
                    on_conflict=conflict,  # type: ignore[arg-type]  # API str; values validated to ON_CONFLICT literals above
                )
            else:
                plan = apply_case_import(
                    skill_path,
                    data,
                    filename=file.filename,
                    on_conflict=conflict,  # type: ignore[arg-type]  # API str; values validated to ON_CONFLICT literals above
                    dry_run=False,
                )
        except CaseImportError as exc:
            fail(
                400,
                exc.message,
                rows=[row.__dict__ for row in exc.rows],
            )
        except SuiteError as exc:
            fail(400, exc.message, hint=exc.hint)
        pack = load_case_pack(skill_path)
        return {
            "skill": skill_payload(state, skill_path),
            "format": plan.format,
            "rows": [row.__dict__ for row in plan.rows],
            "imported_count": len(plan.checks),
            "warnings": plan.warnings,
            "dry_run": dry_run or not confirm,
            "checks": checks_from_pack(pack, include_drafts=True) if pack else [],
            "pack_judge": pack_judge_dict(pack),
        }

    @app.get("/api/evals/dataset")
    def dataset(skill: str, request: Request) -> dict[str, Any]:
        state = state_of(request)
        path = require_under(state.root, find_skill(state.root, skill))
        view = dataset_view(path, include_files=True)
        return view or {"skill": path.name, "cases": [], "tool_checks": None}

    @app.post("/api/evals/fixture-bind")
    async def fixture_bind(
        request: Request,
        payload: EvalFixtureBindBody = Body(),
    ) -> dict[str, Any]:
        state = state_of(request)
        skill_path = require_under(state.root, find_skill(state.root, payload.skill))
        checks = [dict(item) for item in payload.checks]
        inherit = payload.inherit
        glob_pat = payload.glob
        action = payload.action or "inherit"
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
