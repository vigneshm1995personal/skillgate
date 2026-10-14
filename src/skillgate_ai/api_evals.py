"""Load and pin pack checks. Generate never starts a run."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile

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
            from skillgate_ai.pack_edit import apply_pin

            pack, warnings = apply_pin(
                skill_path,
                checks=checks if isinstance(checks, list) else None,
                case_ids=case_ids if isinstance(case_ids, list) else None,
                pack_judge=body.get("pack_judge") if isinstance(body.get("pack_judge"), dict) else None,
                has_pack_judge="pack_judge" in body,
            )
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
        skill_path = find_skill(state.root, skill)
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
                    on_conflict=conflict,  # type: ignore[arg-type]
                )
            else:
                plan = apply_case_import(
                    skill_path,
                    data,
                    filename=file.filename,
                    on_conflict=conflict,  # type: ignore[arg-type]
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
