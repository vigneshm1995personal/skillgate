"""Local FastAPI surface for the React UI. No account. Core never imports cloud."""

from __future__ import annotations

import io
import os
import threading
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from skillgate_ai import __version__
from skillgate_ai.advice import description_from_paste, rewrite_skill_description
from skillgate_ai.case_pack import (
    CASES_REL,
    checks_from_pack,
    dataset_view,
    load_case_pack,
    pin_case_ids,
    pin_checks,
    skill_has_dataset,
)
from skillgate_ai.catalog import catalog_entries, find_skill, import_from_agent_folders
from skillgate_ai.config import ROOT_ENV_NAMES, get_llm_config, load_env, missing_key_error
from skillgate_ai.deploy import deploy_status, get_adapter
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.fixture_bind import apply_inherit, expand_from_folder
from skillgate_ai.gate import run_check
from skillgate_ai.history import load_history
from skillgate_ai.ingest import FRONTMATTER_RE, ingest_skill
from skillgate_ai.live import create_control, drop_control, get_control
from skillgate_ai.local_ui.api import merge_env_file
from skillgate_ai.mode import current_mode, is_local, slots_for
from skillgate_ai.pack import (
    browser_files,
    pack_file_path,
    pack_preview,
    relevant_eval_fixtures,
    write_pack_file,
)
from skillgate_ai.paths import project_root
from skillgate_ai.report import progress_to_dict, report_to_dict
from skillgate_ai.scaffold import scaffold_trigger_cases
from skillgate_ai.skill_md import write_skill_md

SETTINGS_KEYS = (
    "CURSOR_API_KEY",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY",
)
CI_URL = "https://github.com/vigneshm1995personal/skillgate/actions"


@dataclass
class AppState:
    root: Path
    initial_pack: Path | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)


def create_app(*, root: Path | None = None, pack: Path | None = None) -> FastAPI:
    workspace = (root or project_root()).expanduser().resolve()
    load_env(workspace)
    state = AppState(
        root=workspace,
        initial_pack=pack.expanduser().resolve() if pack else None,
    )
    app = FastAPI(title="Skill Gate", version=__version__)
    app.state.ui = state
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost)(:\d+)?",
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(SkillGateError)
    async def _skillgate_error(_request: Request, exc: SkillGateError) -> JSONResponse:
        status = 409 if isinstance(exc, MissingLLMKeyError) else 400
        return JSONResponse(
            status_code=status,
            content={"detail": {"message": exc.message, "hint": exc.hint}},
        )

    @app.exception_handler(FileNotFoundError)
    async def _missing(_request: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"detail": {"message": str(exc) or "File not found."}},
        )

    _register_routes(app)
    return app


def _state(request: Request) -> AppState:
    return request.app.state.ui


def _fail(status: int, message: str, hint: str | None = None, **extra: Any) -> None:
    detail: dict[str, Any] = {"message": message}
    if hint:
        detail["hint"] = hint
    detail.update({key: value for key, value in extra.items() if value is not None})
    raise HTTPException(status_code=status, detail=detail)


def _register_routes(app: FastAPI) -> None:
    @app.get("/api/status")
    def status(request: Request) -> dict[str, Any]:
        state = _state(request)
        load_env(state.root)
        cfg = get_llm_config()
        mode = current_mode()
        missing = missing_key_error()
        skills = catalog_entries(state.root)
        return {
            "version": __version__,
            "mode": mode,
            "slots": slots_for(mode),
            "has_key": cfg.has_any_key,
            "has_gateway_key": bool(cfg.gateway_api_key or cfg.openai_api_key),
            "live_backends": cfg.live_backends,
            "available_harnesses": cfg.available_harnesses,
            "default_harness": cfg.default_harness,
            "missing_key_message": (
                "No model key yet. Run still uses the built-in checker — that is not a live model."
                if is_local(mode) and not cfg.has_any_key
                else (None if cfg.has_any_key else missing.message)
            ),
            "missing_key_hint": (
                "Add a key in Settings to run live. `skillgate check` still exits 0 or 1 with no account."
                if is_local(mode) and not cfg.has_any_key
                else (None if cfg.has_any_key else missing.hint)
            ),
            "auth_required": False,
            "siwv_configured": False,
            "auth_open": False,
            "auth_open_reason": None,
            "ci": {"url": CI_URL, "badge": "", "workflow": "gate.yml"},
            "deploy": deploy_status(),
            "harness_auth": {
                "has_cursor_api_key": bool(cfg.cursor_api_key),
                "has_codex_api_key": bool(cfg.codex_api_key),
                "has_anthropic_api_key": bool(cfg.anthropic_api_key),
                "has_gateway_api_key": bool(cfg.gateway_api_key or cfg.openai_api_key),
                "selected_provider": cfg.default_harness,
            },
            "skills_dir_exists": (state.root / "skills").is_dir(),
            "skills_dir_count": len(skills),
            "catalog_error": None,
        }

    @app.get("/api/auth/me")
    def auth_me() -> dict[str, Any]:
        return {"auth_required": False, "user": None}

    @app.post("/api/auth/signout")
    def auth_signout() -> dict[str, Any]:
        return {}

    @app.get("/api/settings/keys")
    def settings_keys(request: Request) -> dict[str, Any]:
        return {"keys": _keys_payload(_state(request))}

    @app.put("/api/settings/keys/{name}")
    async def set_key(name: str, request: Request) -> dict[str, Any]:
        state = _state(request)
        if name not in SETTINGS_KEYS or name not in ROOT_ENV_NAMES:
            _fail(400, "Unknown key name.")
        body = await request.json()
        value = str((body or {}).get("value") or "").strip()
        if not value:
            _fail(400, "Paste a key before saving.")
        if any(ch in value for ch in "\r\n"):
            _fail(400, "API keys cannot contain line breaks.")
        merge_env_file(state.root / ".env", {name: value})
        os.environ[name] = value
        load_env(state.root)
        return {"keys": _keys_payload(state)}

    @app.delete("/api/settings/keys/{name}")
    def clear_key(name: str, request: Request) -> dict[str, Any]:
        state = _state(request)
        if name not in SETTINGS_KEYS:
            _fail(400, "Unknown key name.")
        merge_env_file(state.root / ".env", {name: ""})
        os.environ.pop(name, None)
        load_env(state.root)
        return {"keys": _keys_payload(state)}

    @app.get("/api/skills")
    def list_skills(request: Request) -> dict[str, Any]:
        state = _state(request)
        skills = [_skill_payload(state, Path(item["absolute"])) for item in catalog_entries(state.root)]
        return {"skills": skills, "catalog_error": None}

    @app.post("/api/skills/import")
    async def import_skills(request: Request) -> dict[str, Any]:
        state = _state(request)
        body = await request.json() if request.headers.get("content-length") not in {None, "0"} else {}
        sources = body.get("sources") if isinstance(body, dict) else None
        result = import_from_agent_folders(
            state.root,
            sources=sources if isinstance(sources, list) else None,
        )
        result["skills"] = [
            _skill_payload(state, Path(item["absolute"])) for item in catalog_entries(state.root)
        ]
        return result

    @app.get("/api/skills/{name}")
    def skill_detail(name: str, request: Request) -> dict[str, Any]:
        state = _state(request)
        path = find_skill(state.root, unquote(name))
        skill = _skill_payload(state, path)
        hist = _history_payload(state, path)
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
        skill = find_skill(_state(request).root, unquote(name))
        return pack_preview(skill, path)

    @app.get("/api/skills/{name}/pack-raw")
    def skill_pack_raw(name: str, path: str, request: Request) -> FileResponse:
        skill = find_skill(_state(request).root, unquote(name))
        file_path = pack_file_path(skill, path)
        return FileResponse(file_path)

    @app.post("/api/skills/pack-file")
    async def write_skill_pack_file(request: Request) -> dict[str, Any]:
        state = _state(request)
        body = await request.json()
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        rel = str(body.get("path") or body.get("filename") or "").strip()
        content = body.get("content")
        if content is None:
            _fail(400, "Pass file content to write.")
        if not rel:
            _fail(400, "Pass a file path inside the skill folder.")
        written = write_pack_file(skill_path, rel=rel, content=str(content))
        return {"skill": _skill_payload(state, skill_path), "file": written}

    @app.post("/api/skills/pack-upload")
    async def pack_upload(
        request: Request,
        skill: str = Form(...),
        file: UploadFile = File(...),
        path: str | None = Form(None),
    ) -> dict[str, Any]:
        state = _state(request)
        skill_path = find_skill(state.root, skill)
        rel = (path or file.filename or "upload.bin").strip()
        data = await file.read()
        written = write_pack_file(skill_path, rel=rel, content=data)
        return {"skill": _skill_payload(state, skill_path), "file": written}

    @app.post("/api/skills/paste")
    async def paste_skill(request: Request) -> dict[str, Any]:
        state = _state(request)
        body = await request.json()
        markdown = str((body or {}).get("markdown") or "").strip()
        if not markdown:
            _fail(400, "Paste a SKILL.md file.")
        path = _write_pasted_skill(state.root, markdown)
        return _skill_payload(state, path)

    @app.post("/api/skills/upload")
    async def upload_zip(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
        state = _state(request)
        data = await file.read()
        path = _extract_uploaded_skill(state.root, data, filename=file.filename or "skill.zip")
        return _skill_payload(state, path)

    @app.post("/api/skills/apply-fix")
    async def apply_fix(request: Request) -> dict[str, Any]:
        state = _state(request)
        body = await request.json()
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        paste = str(body.get("paste") or "").strip()
        if not paste:
            _fail(400, "Pass a SKILL.md paste block.")
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
        return _skill_payload(state, skill_path)

    @app.get("/api/history")
    def history(request: Request, skill: str | None = None) -> dict[str, Any]:
        state = _state(request)
        if skill:
            return _history_payload(state, find_skill(state.root, skill))
        return _workspace_history(state)

    @app.get("/api/analytics")
    def analytics(request: Request, skill: str | None = None) -> dict[str, Any]:
        del skill
        _state(request)
        return {
            "totals": {
                "runs": 0,
                "runs_7d": 0,
                "runs_30d": 0,
                "green": 0,
                "red": 0,
                "skills_evaluated": 0,
                "skills_cleared": 0,
                "deployments": 0,
            },
            "usage": {"runs_with_usage": 0, "tokens_total": None, "cost_usd": None},
            "recent_deploys": [],
            "recent": [],
            "outcomes": [],
        }

    @app.post("/api/evals/generate")
    async def generate(request: Request) -> dict[str, Any]:
        state = _state(request)
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
        skill = _skill_payload(state, skill_path)
        return {
            "skill": skill,
            "checks": checks,
            "yaml": yaml_out,
            "note": note,
            "source": source,
            "warning": None,
            "fixture_defaults": skill.get("fixture_defaults") or [],
        }

    @app.post("/api/evals/pin")
    async def pin(request: Request) -> dict[str, Any]:
        state = _state(request)
        body = await request.json()
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        checks = body.get("checks")
        case_ids = body.get("case_ids")
        if isinstance(checks, list) and checks:
            pack = pin_checks(skill_path, [dict(item) for item in checks])
        elif isinstance(case_ids, list) and case_ids:
            pack = pin_case_ids(skill_path, [str(item) for item in case_ids])
        else:
            _fail(400, "Pin needs checks or case ids.")
        yaml_out = (skill_path / CASES_REL).read_text(encoding="utf-8") if (skill_path / CASES_REL).is_file() else ""
        return {
            "pack": pack.model_dump() if hasattr(pack, "model_dump") else pack,
            "fingerprint": None,
            "checks": checks_from_pack(pack, include_drafts=True),
            "yaml": yaml_out,
            "skill": _skill_payload(state, skill_path),
        }

    @app.post("/api/evals/baseline")
    async def baseline(request: Request) -> dict[str, Any]:
        body = await request.json()
        skill = str(body.get("skill") or "")
        return {
            "skill": skill,
            "baseline": {
                "run_id": body.get("run_id"),
                "source": "manual",
                "resolved": False,
            },
        }

    @app.get("/api/evals/dataset")
    def dataset(skill: str, request: Request) -> dict[str, Any]:
        path = find_skill(_state(request).root, skill)
        view = dataset_view(path)
        return view or {"skill": path.name, "cases": []}

    @app.post("/api/evals/fixture-bind")
    async def fixture_bind(request: Request) -> dict[str, Any]:
        state = _state(request)
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
        skill = _skill_payload(state, skill_path)
        return {
            "skill": skill,
            "checks": bound,
            "fixture_defaults": skill.get("fixture_defaults") or [],
            "inherit": inherit,
            "glob": glob_pat,
        }

    @app.post("/api/evals/promote-draft")
    async def promote_draft(request: Request) -> dict[str, Any]:
        state = _state(request)
        body = await request.json()
        task = body.get("task") or {}
        skill_name = body.get("skill")
        skill_payload = None
        if skill_name:
            skill_payload = _skill_payload(state, find_skill(state.root, str(skill_name)))
        check = {
            "id": str(task.get("id") or "draft"),
            "prompt": str(task.get("prompt") or ""),
            "should_trigger": True,
            "files": task.get("files") or [],
        }
        return {"check": check, "hints": [], "source_task_id": task.get("id"), "skill": skill_payload}

    @app.post("/api/evals/suggest-skill-updates")
    def suggest_updates() -> None:
        _fail(404, "Suggest skill updates isn’t in the local app.")

    @app.post("/api/runs")
    async def start_run(request: Request) -> dict[str, Any]:
        state = _state(request)
        body = await request.json()
        return _start_run(state, body)

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, request: Request) -> dict[str, Any]:
        state = _state(request)
        record = state.runs.get(run_id)
        if record is None:
            found = _run_from_history(state, run_id)
            if found is None:
                _fail(404, f"Unknown run {run_id}")
            return found
        return dict(record)

    @app.post("/api/runs/{run_id}/skip")
    def skip_run(run_id: str) -> dict[str, Any]:
        control = get_control(run_id)
        if control is None:
            _fail(404, f"Unknown run {run_id}")
        control.request_skip()
        return {"ok": True, "id": run_id, "status": "running"}

    @app.post("/api/runs/{run_id}/kill")
    def kill_run(run_id: str) -> dict[str, Any]:
        control = get_control(run_id)
        if control is None:
            _fail(404, f"Unknown run {run_id}")
        control.request_kill()
        return {"ok": True, "id": run_id, "status": "running"}

    @app.post("/api/deploy")
    async def deploy(request: Request) -> dict[str, Any]:
        state = _state(request)
        body = await request.json()
        target = str(body.get("target") or "").strip().lower()
        mode = str(body.get("mode") or "local").strip().lower()
        if mode == "git" or target == "git":
            _fail(404, "Publishing to git isn’t in the local app.")
        skill_path = find_skill(state.root, str(body.get("skill") or ""))
        loaded = ingest_skill(skill_path)
        result = get_adapter(target).install(skill=loaded, source=skill_path)
        return {
            "status": result.get("status") or "installed",
            "note": result.get("message") or f"Installed {loaded.name}",
            "live": True,
            "mode": "local",
            "skill": loaded.name,
            "dest": result.get("dest_path"),
            "attempt": {
                "target": target,
                "status": result.get("status") or "installed",
                "dest_path": result.get("dest_path"),
                "mode": "local",
                "pack_path": result.get("pack_path"),
                "file_count": result.get("file_count"),
            },
        }


def _env_file_keys(root: Path) -> set[str]:
    path = root / ".env"
    found: set[str] = set()
    if not path.is_file():
        return found
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        value = line.split("=", 1)[1].strip()
        if key in SETTINGS_KEYS and value:
            found.add(key)
    return found


def _keys_payload(state: AppState) -> dict[str, Any]:
    load_env(state.root)
    from_file = _env_file_keys(state.root)
    keys: dict[str, Any] = {}
    for name in SETTINGS_KEYS:
        env_set = bool(os.environ.get(name, "").strip())
        saved = name in from_file
        keys[name] = {
            "set": env_set or saved,
            "from_vault": saved,
            "from_env": env_set and not saved,
        }
    return keys


def _skill_payload(state: AppState, path: Path) -> dict[str, Any]:
    loaded = ingest_skill(path)
    files = browser_files(path)
    hist = load_history(path, limit=50)
    last = hist[-1] if hist else None
    last_run = _history_row_to_run(last, path) if last else None
    gate = "pending"
    if last_run:
        gate = last_run.get("gate_decision") or ("cleared" if last_run.get("passed") else "blocked")
    return {
        "id": loaded.name,
        "name": loaded.name,
        "description": loaded.description,
        "path": str(path.relative_to(state.root)) if _is_relative(path, state.root) else path.name,
        "absolute": str(path.resolve()),
        "uploaded": False,
        "seed": loaded.name == "pdf",
        "sabotaged": loaded.name == "pdf-sabotaged",
        "gate": gate,
        "last_eval_at": last.get("ts") if last else None,
        "eval_count": len(hist),
        "deploy_count": 0,
        "version_count": 0,
        "last_run": last_run,
        "last_deploy": None,
        "pack_files": files,
        "fixture_defaults": [
            {"src": item["src"], "dest": item["dest"], "bytes": item.get("bytes")}
            for item in relevant_eval_fixtures(path)
        ],
        "default_output_path": "output/result.txt",
        "has_dataset": skill_has_dataset(path),
    }


def _is_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _history_row_to_run(row: dict[str, Any], skill_path: Path) -> dict[str, Any]:
    report = row.get("report") if isinstance(row.get("report"), dict) else None
    passed = row.get("passed")
    error = row.get("error") if isinstance(row.get("error"), dict) else None
    harness = (report or {}).get("harness")
    if is_local():
        decision = "cleared" if passed else "blocked"
        reason = "Gate is green." if passed else "Gate is red."
    else:
        from skillgate_ai.fixture_bind import decide_gate_result

        verdict = decide_gate_result(
            harness=harness,
            passed=bool(passed),
            status="error" if error else "done",
            skill_path=skill_path,
            report=report,
        )
        decision = verdict.decision
        reason = verdict.reason
    return {
        "id": row.get("run_id"),
        "status": "error" if error else "done",
        "passed": passed,
        "gate": row.get("gate") or ("green" if passed else "red"),
        "gate_decision": decision,
        "gate_reason": reason,
        "error": error,
        "report": report,
        "created_at": row.get("ts"),
        "harness": harness,
        "skill": (report or {}).get("skill") or skill_path.name,
        "skill_path": str(skill_path),
        "config": row.get("config"),
        "completed_count": (report or {}).get("task_count"),
        "task_count": (report or {}).get("task_count"),
        "tryout": bool((report or {}).get("tryout")),
    }


def _history_payload(state: AppState, skill_path: Path) -> dict[str, Any]:
    del state
    rows = load_history(skill_path, limit=50)
    runs = [_history_row_to_run(row, skill_path) for row in reversed(rows)]
    last_run = runs[0] if runs else None
    gate = "pending"
    if last_run:
        gate = last_run.get("gate_decision") or "pending"
    timeline = [
        {
            "kind": "run",
            "id": item.get("id"),
            "at": item.get("created_at"),
            "passed": item.get("passed"),
            "skill": item.get("skill"),
            "harness": item.get("harness"),
            "gate": item.get("gate"),
            "status": item.get("status"),
            "tryout": item.get("tryout"),
        }
        for item in runs
    ]
    return {
        "skill": skill_path.name,
        "gate": gate,
        "last_run": last_run,
        "last_deploy": None,
        "versions": [],
        "runs": runs,
        "deploys": [],
        "timeline": timeline,
        "baseline": None,
    }


def _workspace_history(state: AppState) -> dict[str, Any]:
    timeline: list[dict[str, Any]] = []
    last_run = None
    for entry in catalog_entries(state.root):
        hist = _history_payload(state, Path(entry["absolute"]))
        timeline.extend(hist["timeline"])
        if hist["last_run"] and (
            last_run is None or str(hist["last_run"].get("created_at") or "") > str(last_run.get("created_at") or "")
        ):
            last_run = hist["last_run"]
    timeline.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
    gate = last_run.get("gate_decision") if last_run else "pending"
    return {
        "skill": None,
        "gate": gate or "pending",
        "last_run": last_run,
        "last_deploy": None,
        "versions": [],
        "runs": [],
        "deploys": [],
        "timeline": timeline[:50],
        "baseline": None,
    }


def _run_from_history(state: AppState, run_id: str) -> dict[str, Any] | None:
    for entry in catalog_entries(state.root):
        path = Path(entry["absolute"])
        for row in load_history(path, limit=0):
            if str(row.get("run_id") or "") == run_id:
                return _history_row_to_run(row, path)
    return None


def _gate_from_result(
    *,
    passed: bool | None,
    harness: str | None,
    status: str,
    skill_path: Path,
    report: dict[str, Any] | None,
    tryout: bool,
) -> tuple[str, str]:
    if tryout:
        return "pending", "Single-check runs do not unlock Deploy."
    if is_local():
        if status == "error" or not passed:
            return "blocked", "Gate is red."
        return "cleared", "Gate is green."
    from skillgate_ai.fixture_bind import decide_gate_result

    verdict = decide_gate_result(
        harness=harness,
        passed=bool(passed),
        status=status,
        skill_path=skill_path,
        report=report,
    )
    return verdict.decision, verdict.reason


def _start_run(state: AppState, body: dict[str, Any]) -> dict[str, Any]:
    load_env(state.root)
    skill_raw = str(body.get("skill") or "").strip()
    if not skill_raw:
        _fail(400, "Pick a skill first.")
    skill_path = find_skill(state.root, skill_raw)
    live = bool(body.get("live"))
    demo = bool(body.get("demo"))
    tryout = bool(body.get("tryout"))
    checks = body.get("checks") if isinstance(body.get("checks"), list) else None
    if live and not get_llm_config().has_any_key:
        raise MissingLLMKeyError(
            "No API key found. Run live needs your API key.",
            hint="Add a key in Settings, then press Run. Or run with the built-in checker — that is not a live model.",
        )
    config = body.get("config") if isinstance(body.get("config"), dict) else {}
    with state.lock:
        busy = [item for item in state.runs.values() if item.get("status") == "running"]
        if busy:
            _fail(409, "A check is already running.")
        run_id = uuid.uuid4().hex[:12]
        seed = {
            "id": run_id,
            "status": "running",
            "passed": None,
            "gate": None,
            "gate_decision": "pending",
            "skill": skill_path.name,
            "skill_path": str(skill_path),
            "harness": str(body.get("harness") or "auto"),
            "tryout": tryout,
            "completed_count": 0,
            "task_count": len(checks) if checks else None,
            "current_task_id": None,
            "error": None,
            "report": None,
            "config": config,
            "model": config.get("model"),
            "timeout_sec": config.get("timeout_sec"),
            "temperature": config.get("temperature"),
            "reasoning_effort": config.get("reasoning_effort"),
        }
        state.runs[run_id] = seed
        create_control(run_id)

    def worker() -> None:
        record = state.runs[run_id]
        control = get_control(run_id)
        try:

            def on_progress(progress) -> None:
                payload = progress_to_dict(progress)
                record["report"] = payload
                record["completed_count"] = payload.get("completed_count")
                record["task_count"] = payload.get("task_count")
                record["current_task_id"] = payload.get("current_task_id")
                record["harness"] = payload.get("harness") or record.get("harness")

            result = run_check(
                skill_path,
                harness=str(body.get("harness") or "auto"),
                live=live,
                demo=demo or (not live and not get_llm_config().has_any_key),
                on_progress=on_progress,
                control=control,
                run_id=run_id,
                source="ui",
                root=state.root,
                checks=[dict(item) for item in checks] if checks else None,
                model=config.get("model"),
                timeout=config.get("timeout_sec"),
                temperature=config.get("temperature"),
                reasoning_effort=config.get("reasoning_effort"),
            )
            report = report_to_dict(result.report) if result.report is not None else None
            if report is not None and tryout:
                report["tryout"] = True
            status = "error" if result.error else "done"
            passed = None if result.report is None else result.report.passed
            harness = (report or {}).get("harness") or record.get("harness")
            decision, reason = _gate_from_result(
                passed=passed,
                harness=harness,
                status=status,
                skill_path=skill_path,
                report=report,
                tryout=tryout,
            )
            record.update(
                {
                    "status": status,
                    "passed": passed,
                    "gate": (report or {}).get("gate"),
                    "gate_decision": decision,
                    "gate_reason": reason,
                    "error": result.error,
                    "report": report,
                    "harness": harness,
                    "demo_notice": result.demo_notice,
                    "tryout": tryout,
                    "exit_code": result.exit_code,
                    "completed_count": (report or {}).get("task_count"),
                    "task_count": (report or {}).get("task_count"),
                }
            )
        except Exception as exc:  # noqa: BLE001 — surface to the poller
            message = exc.message if isinstance(exc, SkillGateError) else str(exc)
            record.update(
                {
                    "status": "error",
                    "passed": False,
                    "gate": "red",
                    "gate_decision": "blocked",
                    "error": {"message": message, "hint": getattr(exc, "hint", None)},
                    "tryout": tryout,
                }
            )
        finally:
            drop_control(run_id)

    threading.Thread(target=worker, name=f"skillgate-run-{run_id}", daemon=True).start()
    return {"id": run_id, "status": "running"}


def _write_pasted_skill(root: Path, markdown: str) -> Path:
    text = markdown if markdown.endswith("\n") else markdown + "\n"
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise SkillGateError(
            "Paste a SKILL.md file that starts with YAML frontmatter.",
            hint="First line should be --- then name and description, then --- again.",
        )
    import yaml

    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        raise SkillGateError("SKILL.md frontmatter must be a mapping of fields.")
    name = str(parsed.get("name") or "").strip()
    description = str(parsed.get("description") or "").strip()
    if not name:
        raise SkillGateError("The pasted SKILL.md has no name.")
    parent = root / "skills"
    parent.mkdir(parents=True, exist_ok=True)
    dest = parent / name
    if dest.exists():
        (dest / "SKILL.md").write_text(text, encoding="utf-8")
        ingest_skill(dest)
        return dest
    body = text[match.end() :]
    write_skill_md(dest, name=name, description=description or name, body=body)
    if not (dest / CASES_REL).is_file():
        scaffold_trigger_cases(dest)
    return dest


def _extract_uploaded_skill(root: Path, data: bytes, *, filename: str) -> Path:
    parent = root / "skills"
    parent.mkdir(parents=True, exist_ok=True)
    if filename.endswith(".md") or data.lstrip().startswith(b"---"):
        return _write_pasted_skill(root, data.decode("utf-8"))
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SkillGateError("Upload a zip of a skill folder, or a SKILL.md file.") from exc
    skill_md = None
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if name.endswith("SKILL.md") and not info.is_dir():
            skill_md = name
            break
    if not skill_md:
        raise SkillGateError("That zip has no SKILL.md.")
    parts = Path(skill_md).parts
    prefix = "/".join(parts[:-1])
    folder_name = Path(parts[-2]).name if len(parts) >= 2 else Path(filename).stem
    dest = parent / folder_name
    if dest.exists():
        import shutil

        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir() or ".." in Path(name).parts:
            continue
        rel = name[len(prefix) :].lstrip("/") if prefix and name.startswith(prefix) else name
        if not rel or rel.endswith("/"):
            continue
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(info))
    ingest_skill(dest)
    return dest
