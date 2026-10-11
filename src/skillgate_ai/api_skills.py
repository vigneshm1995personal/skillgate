"""Skill catalog, pack files, import, paste/upload, and local Deploy."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse

from skillgate_ai.advice import description_from_paste, rewrite_skill_description
from skillgate_ai.api_intake import extract_uploaded_skill, write_pasted_skill
from skillgate_ai.api_payloads import fail, history_payload, skill_payload, state_of
from skillgate_ai.catalog import (
    agent_source_status,
    catalog_entries,
    find_skill,
    import_from_agent_folders,
)
from skillgate_ai.deploy import get_adapter
from skillgate_ai.errors import SkillGateError
from skillgate_ai.history import append_deploy
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.pack import (
    CannotSynthesizeFixture,
    pack_file_path,
    pack_preview,
    write_pack_file,
    write_sample_fixture,
)


def _broken_skill_row(item: dict[str, Any]) -> dict[str, Any]:
    folder = Path(str(item.get("absolute") or item.get("name") or "skill"))
    return {
        "id": item.get("id") or item.get("name") or folder.name,
        "name": item.get("name") or folder.name,
        "slug": item.get("slug") or folder.name,
        "description": item.get("description") or "",
        "warning": item.get("warning") or "Couldn't read this skill’s details.",
        "path": item.get("path") or folder.name,
        "absolute": item.get("absolute") or str(folder),
        "uploaded": False,
        "seed": False,
        "sabotaged": False,
        "gate": "pending",
        "pack_files": [],
    }


def register_skill_routes(app: FastAPI) -> None:
    @app.get("/api/skills")
    def list_skills(request: Request) -> dict[str, Any]:
        state = state_of(request)
        skills: list[dict[str, Any]] = []
        for item in catalog_entries(state.root):
            try:
                skills.append(skill_payload(state, Path(item["absolute"])))
            except (SkillGateError, OSError, ValueError):
                skills.append(_broken_skill_row(item))
        return {"skills": skills, "catalog_error": None, "sources": agent_source_status()}

    @app.get("/api/skills/import-sources")
    def import_sources() -> dict[str, Any]:
        return {"sources": agent_source_status()}

    @app.post("/api/skills/import")
    async def import_skills(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json() if request.headers.get("content-length") not in {None, "0"} else {}
        sources = body.get("sources") if isinstance(body, dict) else None
        result = import_from_agent_folders(
            state.root,
            sources=sources if isinstance(sources, list) else None,
        )
        skills: list[dict[str, Any]] = []
        for item in catalog_entries(state.root):
            try:
                skills.append(skill_payload(state, Path(item["absolute"])))
            except (SkillGateError, OSError, ValueError):
                skills.append(_broken_skill_row(item))
        result["skills"] = skills
        result["sources"] = agent_source_status()
        return result

    @app.get("/api/skills/{name}")
    def skill_detail(name: str, request: Request) -> dict[str, Any]:
        state = state_of(request)
        path = find_skill(state.root, unquote(name))
        skill = skill_payload(state, path)
        hist = history_payload(state, path)
        return {
            "skill": skill,
            "gate": hist["gate"],
            "last_run": hist["last_run"],
            "last_deploy": hist["last_deploy"],
            "versions": hist["versions"],
            "runs": hist.get("runs") or [],
            "deploys": hist.get("deploys") or [],
            "timeline": hist["timeline"],
            "pack_files": skill.get("pack_files") or [],
        }

    @app.get("/api/skills/{name}/pack-file")
    def skill_pack_file(name: str, path: str, request: Request) -> dict[str, Any]:
        skill = find_skill(state_of(request).root, unquote(name))
        return pack_preview(skill, path)

    @app.get("/api/skills/{name}/pack-raw")
    def skill_pack_raw(name: str, path: str, request: Request) -> FileResponse:
        skill = find_skill(state_of(request).root, unquote(name))
        return FileResponse(pack_file_path(skill, path))

    @app.post("/api/skills/pack-file")
    async def write_skill_pack_file(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        if body.get("generate"):
            try:
                written = write_sample_fixture(
                    skill_path,
                    dest=str(body.get("path") or body.get("filename") or "").strip() or None,
                    prompt=str(body.get("prompt") or ""),
                    description=ingest_skill(skill_path).description,
                )
            except CannotSynthesizeFixture as exc:
                return {
                    "skill": skill_payload(state, skill_path),
                    "file": None,
                    "needs_upload": True,
                    "message": str(exc),
                }
            return {"skill": skill_payload(state, skill_path), "file": written}
        rel = str(body.get("path") or body.get("filename") or "").strip()
        content = body.get("content")
        if content is None:
            fail(400, "Pass file content to write.")
        if not rel:
            fail(400, "Pass a file path inside the skill folder.")
        written = write_pack_file(skill_path, rel=rel, content=str(content))
        return {"skill": skill_payload(state, skill_path), "file": written}

    @app.post("/api/skills/pack-upload")
    async def pack_upload(
        request: Request,
        skill: str = Form(...),
        file: UploadFile = File(...),
        path: str | None = Form(None),
    ) -> dict[str, Any]:
        state = state_of(request)
        skill_path = find_skill(state.root, skill)
        rel = (path or file.filename or "upload.bin").strip()
        data = await file.read()
        written = write_pack_file(skill_path, rel=rel, content=data)
        return {"skill": skill_payload(state, skill_path), "file": written}

    @app.post("/api/skills/paste")
    async def paste_skill(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        markdown = str((body or {}).get("markdown") or "").strip()
        if not markdown:
            fail(400, "Paste a SKILL.md file.")
        path = write_pasted_skill(state.root, markdown)
        return skill_payload(state, path)

    @app.post("/api/skills/upload")
    async def upload_zip(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
        state = state_of(request)
        data = await file.read()
        path = extract_uploaded_skill(state.root, data, filename=file.filename or "skill.zip")
        return skill_payload(state, path)

    @app.post("/api/skills/apply-fix")
    async def apply_fix(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        paste = str(body.get("paste") or "").strip()
        if not paste:
            fail(400, "Pass a SKILL.md paste block.")
        description = description_from_paste(paste) if paste.lstrip().startswith("---") else paste
        rewrite_skill_description(skill_path / "SKILL.md", description)
        restore = str(body.get("restore_scripts_from") or "").strip()
        if restore:
            try:
                source = find_skill(state.root, restore)
            except SkillGateError:
                source = None
            if source is not None:
                src_scripts = source / "scripts"
                dest_scripts = skill_path / "scripts"
                if src_scripts.is_dir():
                    import shutil

                    if dest_scripts.exists():
                        shutil.rmtree(dest_scripts)
                    shutil.copytree(src_scripts, dest_scripts)
        return skill_payload(state, skill_path)

    @app.get("/api/history")
    def history(request: Request, skill: str | None = None) -> dict[str, Any]:
        from skillgate_ai.api_payloads import workspace_history

        state = state_of(request)
        if skill:
            return history_payload(state, find_skill(state.root, skill))
        return workspace_history(state)

    @app.post("/api/deploy")
    async def deploy(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        target = str(body.get("target") or "").strip().lower()
        mode = str(body.get("mode") or "local").strip().lower()
        if mode == "git" or target == "git":
            fail(404, "Publishing to git isn’t in the local app.")
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        loaded = ingest_skill(skill_path, strict=False)
        result = get_adapter(target).install(skill=loaded, source=skill_path)
        status = result.get("status") or "installed"
        append_deploy(
            skill_path,
            target=target,
            status=status,
            file_count=result.get("file_count"),
            mode="local",
        )
        return {
            "status": status,
            "note": result.get("message") or f"Installed {loaded.name}",
            "live": True,
            "mode": "local",
            "skill": loaded.name,
            "attempt": {
                "target": target,
                "status": status,
                "mode": "local",
                "file_count": result.get("file_count"),
            },
        }
