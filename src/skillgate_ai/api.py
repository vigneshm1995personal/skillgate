"""Local FastAPI app factory. Core never imports cloud."""

from __future__ import annotations

import os
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
from skillgate_ai.api_runs import register_run_routes
from skillgate_ai.api_shims import register_hosted_shims
from skillgate_ai.api_skills import register_skill_routes
from skillgate_ai.catalog import catalog_entries
from skillgate_ai.config import ROOT_ENV_NAMES, get_llm_config, load_env, merge_env_file, missing_key_error
from skillgate_ai.deploy import deploy_status
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.mode import current_mode, is_local, slots_for
from skillgate_ai.paths import project_root


def create_app(*, root: Path | None = None, pack: Path | None = None) -> FastAPI:
    del pack
    workspace = (root or project_root()).expanduser().resolve()
    load_env(workspace)
    app = FastAPI(title="Skill Gate", version=__version__)
    app.state.ui = AppState(root=workspace)
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
    register_hosted_shims(app)
    return app


def _register_core_routes(app: FastAPI) -> None:
    @app.get("/api/status")
    def status(request: Request) -> dict[str, Any]:
        state = state_of(request)
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
            "ci": {"url": "", "badge": "", "workflow": ""},
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

    @app.get("/api/settings/keys")
    def settings_keys(request: Request) -> dict[str, Any]:
        return {"keys": keys_payload(state_of(request))}

    @app.put("/api/settings/keys/{name}")
    async def set_key(name: str, request: Request) -> dict[str, Any]:
        state = state_of(request)
        if name not in SETTINGS_KEYS or name not in ROOT_ENV_NAMES:
            fail(400, "Unknown key name.")
        body = await request.json()
        value = str((body or {}).get("value") or "").strip()
        if not value:
            fail(400, "Paste a key before saving.")
        if any(ch in value for ch in "\r\n"):
            fail(400, "API keys cannot contain line breaks.")
        merge_env_file(state.root / ".env", {name: value})
        os.environ[name] = value
        load_env(state.root)
        return {"keys": keys_payload(state)}

    @app.delete("/api/settings/keys/{name}")
    def clear_key(name: str, request: Request) -> dict[str, Any]:
        state = state_of(request)
        if name not in SETTINGS_KEYS:
            fail(400, "Unknown key name.")
        merge_env_file(state.root / ".env", {name: ""})
        os.environ.pop(name, None)
        load_env(state.root)
        return {"keys": keys_payload(state)}
