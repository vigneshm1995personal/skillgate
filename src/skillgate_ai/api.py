"""Local FastAPI app factory. Core never imports cloud."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from skillgate_ai import __version__
from skillgate_ai.api_evals import register_eval_routes
from skillgate_ai.api_payloads import (
    SETTINGS_KEYS,
    AppState,
    fail,
    keys_payload,
    state_of,
)
from skillgate_ai.api_compare import register_compare_routes
from skillgate_ai.api_runs import register_run_routes
from skillgate_ai.api_shims import register_hosted_shims
from skillgate_ai.api_skills import register_skill_routes
from skillgate_ai.catalog import catalog_entries
from skillgate_ai.config import (
    UI_NO_KEY_HINT,
    get_llm_config,
    load_env,
    missing_key_error,
)
from skillgate_ai.keys import clear_vault_key, set_vault_key
from skillgate_ai.local_guard import LocalUIGuard
from skillgate_ai.deploy import deploy_status
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.mode import current_mode, slots_for
from skillgate_ai.paths import project_root


def _package_git_cwd() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here, *here.parents):
        if (candidate / ".git").exists():
            return candidate
    return here.parents[2] if len(here.parents) >= 2 else Path.cwd()


def ui_build_id() -> str:
    for key in ("SKILLGATE_BUILD", "GITHUB_SHA"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value[:12]
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=_package_git_cwd(),
            stderr=subprocess.DEVNULL,
            timeout=1,
        )
        return out.decode().strip()
    except Exception:
        return ""


def _harness_auth_rows(cfg) -> list[dict[str, Any]]:
    from skillgate_ai.harness import harness_auth_status

    return harness_auth_status(cfg)


def _harness_auth_payload(cfg) -> dict[str, Any]:
    return {
        "has_cursor_api_key": bool(cfg.cursor_api_key),
        "has_codex_api_key": bool(cfg.codex_api_key),
        "has_anthropic_api_key": bool(cfg.anthropic_api_key),
        "selected_provider": cfg.default_harness,
        "harnesses": _harness_auth_rows(cfg),
    }


def create_app(*, root: Path | None = None, pack: Path | None = None) -> FastAPI:
    del pack
    workspace = (root or project_root()).expanduser().resolve()
    load_env(workspace)
    app = FastAPI(title="Skill Gate", version=__version__)
    app.state.ui = AppState(root=workspace)
    app.add_middleware(LocalUIGuard)
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

    _register_core_routes(app)
    register_skill_routes(app)
    register_eval_routes(app)
    register_run_routes(app)
    register_compare_routes(app)
    register_hosted_shims(app)
    return app


def _supported_models_payload() -> dict[str, list[str]]:
    from skillgate_ai.harness import ClaudeCodeHarness, CodexCliHarness, CursorAgentHarness

    return {
        "cursor-agent": list(CursorAgentHarness.supported_models),
        "codex": list(CodexCliHarness.supported_models),
        "claude": list(ClaudeCodeHarness.supported_models),
    }


def _register_core_routes(app: FastAPI) -> None:
    @app.get("/api/status")
    def status(request: Request) -> dict[str, Any]:
        state = state_of(request)
        load_env(state.root)
        cfg = get_llm_config(state.root)
        mode = current_mode()
        missing = missing_key_error()
        skills = catalog_entries(state.root)
        return {
            "version": __version__,
            "build": ui_build_id(),
            "mode": mode,
            "slots": slots_for(mode),
            "has_key": cfg.has_any_key,
            "available_harnesses": cfg.available_harnesses,
            "default_harness": cfg.default_harness,
            "missing_key_message": None if cfg.has_any_key else missing.message,
            "missing_key_hint": None if cfg.has_any_key else UI_NO_KEY_HINT,
            "auth_required": False,
            "siwv_configured": False,
            "auth_open": False,
            "auth_open_reason": None,
            "ci": {"url": "", "badge": "", "workflow": ""},
            "deploy": deploy_status(),
            "harness_auth": _harness_auth_payload(cfg),
            "supported_models": _supported_models_payload(),
            "skills_dir_exists": (state.root / "skills").is_dir(),
            "skills_dir_count": len(skills),
            "catalog_error": None,
        }

    @app.get("/api/settings/keys")
    def settings_keys(request: Request) -> dict[str, Any]:
        return {"keys": keys_payload(state_of(request))}

    @app.put("/api/settings/keys/{name}")
    async def set_key(name: str, request: Request) -> dict[str, Any]:
        state = state_of(request)
        from skillgate_ai.keys import internal_key_name

        vault_name = internal_key_name(name)
        if vault_name not in SETTINGS_KEYS:
            fail(400, "Unknown key name.")
        body = await request.json()
        value = str((body or {}).get("value") or "").strip()
        if not value:
            fail(400, "Paste a key before saving.")
        if any(ch in value for ch in "\r\n"):
            fail(400, "API keys cannot contain line breaks.")
        set_vault_key(state.root, vault_name, value)
        return {"keys": keys_payload(state)}

    @app.get("/api/login/status")
    def login_status(request: Request) -> dict[str, Any]:
        state = state_of(request)
        load_env(state.root)
        cfg = get_llm_config(state.root)
        return {"harnesses": _harness_auth_rows(cfg)}

    @app.post("/api/login/{agent}")
    def start_login(agent: str, request: Request) -> dict[str, Any]:
        from skillgate_ai.harness import normalize_login_agent, run_official_login

        state = state_of(request)
        load_env(state.root)
        kind = normalize_login_agent(agent)
        if kind is None:
            fail(400, "Use cursor, claude, or codex.")
        cfg = get_llm_config(state.root)
        result = run_official_login(kind, cfg)
        installed = bool(result.get("installed"))
        return {
            "agent": result.get("agent") or kind,
            "installed": installed,
            "install": str(result.get("install") or ""),
            "command": str(result.get("command") or f"skillgate login {kind}"),
            "auth": "cli_login" if result.get("ok") else "none",
            "status": result.get("status") or "none",
            "ok": bool(result.get("ok")),
            "needs_terminal": not installed,
            "message": str(result.get("message") or ""),
        }

    @app.delete("/api/settings/keys/{name}")
    def clear_key(name: str, request: Request) -> dict[str, Any]:
        state = state_of(request)
        from skillgate_ai.keys import internal_key_name

        vault_name = internal_key_name(name)
        if vault_name not in SETTINGS_KEYS:
            fail(400, "Unknown key name.")
        clear_vault_key(state.root, vault_name)
        return {"keys": keys_payload(state)}

    @app.get("/api/settings/judge")
    def get_judge_settings(request: Request) -> dict[str, Any]:
        from skillgate_ai.judge_settings import load_judge_settings

        state = state_of(request)
        settings = load_judge_settings(state.root)
        return {"judge": settings.to_public_dict()}

    @app.put("/api/settings/judge")
    async def put_judge_settings(request: Request) -> dict[str, Any]:
        from skillgate_ai.judge_settings import save_judge_settings

        state = state_of(request)
        body = await request.json() or {}
        try:
            settings = save_judge_settings(
                state.root,
                provider=str(body.get("provider") or "auto"),
                region=body.get("region"),
                model=body.get("model"),
                base_url=body.get("base_url"),
                decisions_path=body.get("decisions_path"),
            )
        except SkillGateError as exc:
            fail(400, exc.message, hint=exc.hint)
        return {"judge": settings.to_public_dict()}

    @app.post("/api/judge/ping")
    def ping_scoring(request: Request) -> dict[str, Any]:
        from skillgate_ai.judge import ping_judge

        state = state_of(request)
        try:
            result = ping_judge(get_llm_config(state.root))
        except SkillGateError as exc:
            fail(400, exc.message, hint=exc.hint)
        return result
