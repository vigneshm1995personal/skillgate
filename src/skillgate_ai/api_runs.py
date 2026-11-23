"""Start and poll local runs. Nothing starts until the client POSTs /api/runs."""

from __future__ import annotations

from typing import Any

from skillgate_ai.extras import UI_FEATURE, MissingExtraError

try:
    from fastapi import FastAPI, Request
except ModuleNotFoundError as exc:
    raise MissingExtraError(UI_FEATURE, "ui") from exc

from skillgate_ai.api_payloads import (
    AppState,
    fail,
    run_from_history,
    scrub_browser_payload,
    state_of,
)
from skillgate_ai.catalog import find_skill
from skillgate_ai.config import get_llm_config, load_env, missing_key_error
from skillgate_ai.live import get_control
from skillgate_ai.run_registry import RunRegistry, RunRequest
from skillgate_ai.run_registry import attach_stamped_config as attach_stamped_config


def start_run(state: AppState, body: dict[str, Any]) -> dict[str, Any]:
    load_env(state.root)
    skill_raw = str(body.get("skill") or "").strip()
    if not skill_raw:
        fail(400, "Pick a skill first.")
    skill_path = find_skill(state.root, skill_raw)
    tryout = bool(body.get("tryout"))
    checks = body.get("checks") if isinstance(body.get("checks"), list) else None
    if not get_llm_config(state.root).has_any_key:
        raise missing_key_error()
    raw_config = body.get("config")
    config: dict[str, Any] = raw_config if isinstance(raw_config, dict) else {}
    if state.gate_busy():
        fail(409, "A check or compare is already running.")
    registry = RunRegistry(state.root, runs=state.runs, lock=state.lock, busy=state.gate_busy)
    return registry.start(
        RunRequest(
            skill_path=skill_path,
            harness=str(body.get("harness") or "auto"),
            checks=[dict(item) for item in checks] if checks else None,
            config=config,
            tryout=tryout,
            no_judge=bool(body.get("no_judge")),
            source="ui",
        )
    )


def register_run_routes(app: FastAPI) -> None:
    @app.post("/api/runs")
    async def post_run(request: Request) -> dict[str, Any]:
        return start_run(state_of(request), await request.json())

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str, request: Request) -> dict[str, Any]:
        state = state_of(request)
        record = state.runs.get(run_id)
        if record is None:
            found = run_from_history(state, run_id)
            if found is None:
                fail(404, f"Unknown run {run_id}")
            return found
        return scrub_browser_payload(record)

    @app.post("/api/runs/{run_id}/skip")
    def skip_run(run_id: str) -> dict[str, Any]:
        control = get_control(run_id)
        if control is None:
            fail(404, f"Unknown run {run_id}")
        control.request_skip()
        return {"ok": True, "id": run_id, "status": "running"}

    @app.post("/api/runs/{run_id}/kill")
    def kill_run(run_id: str) -> dict[str, Any]:
        control = get_control(run_id)
        if control is None:
            fail(404, f"Unknown run {run_id}")
        control.request_kill()
        return {"ok": True, "id": run_id, "status": "running"}
