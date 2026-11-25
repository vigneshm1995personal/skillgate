"""Skill catalog, pack files, import, paste/upload, and local Deploy."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, NotRequired, TypedDict
from urllib.parse import unquote

from skillgate_ai.extras import UI_FEATURE, MissingExtraError

try:
    from fastapi import Body, FastAPI, File, Form, Request, UploadFile
    from fastapi.responses import FileResponse
except ModuleNotFoundError as exc:
    raise MissingExtraError(UI_FEATURE, "ui") from exc

from skillgate_ai.advice import description_from_paste, rewrite_skill_description
from skillgate_ai.api_intake import (
    extract_uploaded_skill,
    import_path_or_git_result,
    write_pasted_skill,
)
from skillgate_ai.api_models import (
    ApplyFixBody,
    DeployBody,
    ImportSkillsBody,
    InstallExamplesBody,
    PackFileWriteBody,
    PasteSkillBody,
)
from skillgate_ai.api_payloads import AppState, fail, history_payload, skill_payload, state_of
from skillgate_ai.catalog import (
    agent_source_status,
    catalog_entries,
    find_skill,
    import_from_agent_folders,
    workspace_skills_root,
)
from skillgate_ai.config import get_llm_config, missing_key_error
from skillgate_ai.deploy import get_adapter, require_passing_check
from skillgate_ai.errors import SkillGateError
from skillgate_ai.examples import install_examples, list_examples
from skillgate_ai.history import append_deploy
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.pack import (
    CannotSynthesizeFixture,
    pack_file_path,
    pack_preview,
    write_pack_file,
    write_sample_fixture,
)
from skillgate_ai.paths import require_under

_PICKER_SOURCE_LABELS = {
    "workspace": "This project",
    "cursor": "Editor agent",
    "codex": "Terminal agent",
    "claude": "Code agent",
}


class BrokenSkillRow(TypedDict):
    id: str
    name: str
    slug: str
    description: str
    warning: str
    path: str
    absolute: str
    uploaded: bool
    seed: bool
    sabotaged: bool
    gate: str
    pack_files: list[Mapping[str, Any]]
    source: NotRequired[str]
    source_label: NotRequired[str]


def _broken_skill_row(item: Mapping[str, Any]) -> BrokenSkillRow:
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


def _listed_skill(state: AppState, item: Mapping[str, Any]) -> Mapping[str, Any]:
    payload: Mapping[str, Any]
    try:
        payload = skill_payload(state, Path(item["absolute"]))
    except (SkillGateError, OSError, ValueError):
        payload = _broken_skill_row(item)
    source = str(item.get("source") or "")
    return {
        **payload,
        "source": source,
        "source_label": _PICKER_SOURCE_LABELS.get(source, str(item.get("source_label") or source)),
    }


def _listed_skills(state: AppState) -> list[Mapping[str, Any]]:
    return [_listed_skill(state, item) for item in catalog_entries(state.root, include_agents=True)]


def register_skill_routes(app: FastAPI) -> None:
    @app.get("/api/examples")
    def list_dataset_examples() -> dict[str, Any]:
        return {"examples": list_examples()}

    @app.post("/api/examples/install")
    async def install_dataset_examples(
        request: Request,
        install: InstallExamplesBody | None = Body(None),
    ) -> dict[str, Any]:
        state = state_of(request)
        payload = install or InstallExamplesBody()
        raw_names = payload.names
        name = str(payload.name or "").strip()
        names: list[str] | None
        if isinstance(raw_names, list) and raw_names:
            names = [str(item).strip() for item in raw_names if str(item).strip()]
        elif name:
            names = [name]
        else:
            names = None
        result = install_examples(workspace_skills_root(state.root), names)
        result["skills"] = _listed_skills(state)
        return result

    @app.get("/api/skills")
    def list_skills(request: Request) -> dict[str, Any]:
        state = state_of(request)
        return {
            "skills": _listed_skills(state),
            "catalog_error": None,
            "sources": agent_source_status(),
        }

    @app.get("/api/skills/import-sources")
    def import_sources() -> dict[str, Any]:
        return {"sources": agent_source_status()}

    @app.post("/api/skills/import")
    async def import_skills(
        request: Request,
        import_body: ImportSkillsBody | None = Body(None),
    ) -> dict[str, Any]:
        state = state_of(request)
        payload = import_body or ImportSkillsBody()
        folder = str(payload.folder or payload.path or "").strip()
        git_url = str(payload.git_url or payload.git or "").strip()
        if folder or git_url:
            result = import_path_or_git_result(state.root, git_url or folder)
        else:
            sources = payload.sources
            result = import_from_agent_folders(
                state.root,
                sources=sources if isinstance(sources, list) else None,
            )
        result["skills"] = _listed_skills(state)
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
    async def write_skill_pack_file(
        request: Request,
        payload: PackFileWriteBody = Body(),
    ) -> dict[str, Any]:
        state = state_of(request)
        skill_path = find_skill(state.root, payload.skill)
        if payload.generate:
            try:
                written = write_sample_fixture(
                    skill_path,
                    dest=str(payload.path or payload.filename or "").strip() or None,
                    prompt=payload.prompt,
                    description=ingest_skill(skill_path).description,
                )
            except CannotSynthesizeFixture:
                return {
                    "skill": skill_payload(state, skill_path),
                    "file": None,
                    "needs_upload": True,
                    "message": (
                        "This check needs a real photo or scan — "
                        "upload one instead of a generated sample."
                    ),
                }
            return {"skill": skill_payload(state, skill_path), "file": written}
        rel = str(payload.path or payload.filename or "").strip()
        content = payload.content
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
    async def paste_skill(request: Request, payload: PasteSkillBody = Body()) -> dict[str, Any]:
        state = state_of(request)
        markdown = payload.markdown.strip()
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
    async def apply_fix(request: Request, payload: ApplyFixBody = Body()) -> dict[str, Any]:
        state = state_of(request)
        skill_path = require_under(state.root, find_skill(state.root, payload.skill))
        paste = payload.paste.strip()
        if not paste:
            fail(400, "Pass a SKILL.md paste block.")
        description = description_from_paste(paste) if paste.lstrip().startswith("---") else paste
        rewrite_skill_description(skill_path / "SKILL.md", description)
        restore = payload.restore_scripts_from.strip()
        if restore:
            try:
                source = require_under(state.root, find_skill(state.root, restore))
            except SkillGateError:
                source = None
            if source is not None:
                import os

                from skillgate_ai.pack_io import write_pack_bytes
                from skillgate_ai.paths import contained_path, pack_path_string

                src_root = pack_path_string(source, "scripts")
                require_under(source, contained_path(source, "scripts"))
                if os.path.isdir(src_root):
                    for dirpath, _, filenames in os.walk(src_root, followlinks=False):
                        for name in filenames:
                            abs_src = os.path.join(dirpath, name)
                            rel = os.path.relpath(abs_src, src_root).replace("\\", "/")
                            dest_rel = f"scripts/{rel}"
                            rel_src = f"scripts/{rel}"
                            src_path = pack_path_string(source, rel_src)
                            with open(src_path, "rb") as handle:
                                file_bytes = handle.read()
                            write_pack_bytes(skill_path, dest_rel, file_bytes)
        return skill_payload(state, skill_path)

    @app.get("/api/history")
    def history(request: Request, skill: str | None = None) -> dict[str, Any]:
        from skillgate_ai.api_payloads import workspace_history

        state = state_of(request)
        if skill:
            return history_payload(state, find_skill(state.root, skill))
        return workspace_history(state)

    @app.post("/api/deploy")
    async def deploy(request: Request, payload: DeployBody = Body()) -> dict[str, Any]:
        state = state_of(request)
        target = payload.target.strip().lower()
        mode = payload.mode.strip().lower()
        if mode == "git" or target == "git":
            fail(404, "Publishing to git isn’t in the local app.")
        skill_path = find_skill(state.root, payload.skill)
        loaded = ingest_skill(skill_path, strict=False)
        require_passing_check(
            skill_path,
            name=loaded.name,
            force=payload.force,
        )
        if not get_llm_config(state.root).has_any_key:
            raise missing_key_error()
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
