"""Start and poll local runs. Nothing starts until the client POSTs /api/runs."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from fastapi import FastAPI, Request

from skillgate_ai.api_payloads import (
    AppState,
    fail,
    local_gate,
    run_from_history,
    scrub_browser_payload,
    state_of,
)
from skillgate_ai.catalog import find_skill
from skillgate_ai.config import NO_KEY_HINT, get_llm_config, load_env
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.gate import run_check
from skillgate_ai.live import create_control, drop_control, get_control
from skillgate_ai.report import progress_to_dict, report_to_dict


def attach_stamped_config(record: dict[str, Any], report: dict[str, Any] | None) -> None:
    """Replace the request config with the resolved stamp so UI Result/Metrics match the run."""
    stamped = report.get("config") if isinstance(report, dict) else None
    if isinstance(stamped, dict):
        record["config"] = stamped


def start_run(state: AppState, body: dict[str, Any]) -> dict[str, Any]:
    load_env(state.root)
    skill_raw = str(body.get("skill") or "").strip()
    if not skill_raw:
        fail(400, "Pick a skill first.")
    skill_path = find_skill(state.root, skill_raw)
    tryout = bool(body.get("tryout"))
    checks = body.get("checks") if isinstance(body.get("checks"), list) else None
    if not get_llm_config(state.root).has_any_key:
        raise MissingLLMKeyError(
            "No model key found.",
            hint=NO_KEY_HINT,
        )
    config = body.get("config") if isinstance(body.get("config"), dict) else {}
    if state.gate_busy():
        fail(409, "A check or compare is already running.")
    with state.lock:
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

            pref = str(config.get("harness_pref") or "").strip().lower()
            requested = str(body.get("harness") or "").strip().lower()
            harness = pref if pref in {"auto", "cursor-agent", "codex", "claude", "llm"} else (requested or "auto")
            result = run_check(
                skill_path,
                harness=harness,
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
                tryout=tryout,
            )
            report = report_to_dict(result.report) if result.report is not None else None
            if report is not None and tryout:
                report["tryout"] = True
            status = "error" if result.error else "done"
            passed = None if result.report is None else result.report.passed
            harness = (report or {}).get("harness") or record.get("harness")
            decision, reason = local_gate(passed, status=status, tryout=tryout)
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
            attach_stamped_config(record, report)
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
