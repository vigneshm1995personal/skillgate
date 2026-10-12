"""Compare API routes (models + versions)."""

from __future__ import annotations

import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request

from skillgate_ai.api_payloads import AppState, fail, state_of
from skillgate_ai.catalog import find_skill
from skillgate_ai.compare import (
    CompareArmSpec,
    CompareError,
    arm_id_for_index,
    arm_label_defaults,
    find_compare,
    find_compare_anywhere,
    list_compares,
    parse_arm_spec,
    run_models_compare,
    run_versions_compare,
    scrub_compare_payload,
    scrub_customer_compare_payload,
)
from skillgate_ai.compare_control import request_cancel_compare
from skillgate_ai.config import get_llm_config, load_env
from skillgate_ai.errors import MissingLLMKeyError


def _finish_compare_job(
    state: AppState,
    compare_id: str,
    result: Any,
) -> None:
    payload = scrub_customer_compare_payload(result.payload)
    payload["status"] = str(result.payload.get("status") or "done")
    with state.lock:
        state.compares[compare_id] = payload


def _fail_compare_job(
    state: AppState,
    compare_id: str,
    *,
    message: str,
    hint: str | None = None,
) -> None:
    with state.lock:
        state.compares[compare_id] = {
            "compare_id": compare_id,
            "status": "error",
            "error": {"message": message, "hint": hint},
        }


def register_compare_routes(app: FastAPI) -> None:
    @app.get("/api/compare")
    def get_compares(request: Request, skill: str) -> dict[str, Any]:
        state = state_of(request)
        path = find_skill(state.root, skill)
        rows = list_compares(path, limit=20)
        return {
            "skill": path.name,
            "compares": [scrub_customer_compare_payload(row) for row in reversed(rows)],
        }

    @app.get("/api/compare/{compare_id}")
    def get_compare(compare_id: str, request: Request, skill: str | None = None) -> dict[str, Any]:
        state = state_of(request)
        row = None
        if skill:
            path = find_skill(state.root, skill)
            row = find_compare(path, compare_id)
        else:
            found = find_compare_anywhere(state.root, compare_id)
            if found:
                path, row = found
        if row is None:
            with state.lock:
                live = state.compares.get(compare_id)
            if live:
                return scrub_customer_compare_payload(live)
            fail(404, f"Unknown compare {compare_id}")
        return scrub_customer_compare_payload(row)

    @app.post("/api/compare/models")
    async def post_compare_models(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        return _start_models_compare(state, body)

    @app.post("/api/compare/versions")
    async def post_compare_versions(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        return _start_versions_compare(state, body)

    @app.post("/api/compare/{compare_id}/cancel")
    def post_compare_cancel(compare_id: str, request: Request) -> dict[str, Any]:
        state = state_of(request)
        request_cancel_compare(state.root, compare_id)
        with state.lock:
            live = state.compares.get(compare_id)
            if live and live.get("status") == "running":
                live["status"] = "cancelling"
        return {"ok": True, "compare_id": compare_id, "status": "cancelling"}


def _start_models_compare(state: AppState, body: dict[str, Any]) -> dict[str, Any]:
    load_env(state.root)
    skill_raw = str(body.get("skill") or "").strip()
    if not skill_raw:
        fail(400, "Pick a skill first.")
    if not get_llm_config(state.root).has_any_key:
        raise MissingLLMKeyError(
            "No model key found.",
            hint="Add a key in Settings (`skillgate ui`) or run `skillgate keys set`.",
        )
    if state.gate_busy():
        fail(409, "A check or compare is already running.")
    path = find_skill(state.root, skill_raw)
    raw_arms = body.get("arms")
    if not isinstance(raw_arms, list) or len(raw_arms) < 2:
        fail(400, "Add at least two arms.")
    specs: list[CompareArmSpec] = []
    for index, item in enumerate(raw_arms[:4]):
        arm_id = arm_id_for_index(index)
        if isinstance(item, str):
            specs.append(parse_arm_spec(item, arm_id=arm_id, index=index))
        elif isinstance(item, dict):
            label = str(item.get("label") or arm_label_defaults(len(raw_arms))[index])
            specs.append(
                CompareArmSpec(
                    arm_id=arm_id,
                    label=label,
                    harness_pref=str(item.get("harness_pref") or item.get("harness") or "auto"),
                    model=item.get("model"),
                    timeout_sec=item.get("timeout_sec"),
                    temperature=item.get("temperature"),
                    reasoning_effort=item.get("reasoning_effort"),
                )
            )
        else:
            fail(400, "Each arm must be a string or object.")
    cap = body.get("max_spend_usd")
    max_spend = float(cap) if cap is not None else 5.0
    compare_id = uuid.uuid4().hex[:12]
    seed = {"compare_id": compare_id, "status": "running", "mode": "models", "skill": path.name}
    with state.lock:
        state.compares[compare_id] = seed

    def worker() -> None:
        try:
            result = run_models_compare(
                path,
                arms=specs,
                root=state.root,
                max_spend_usd=max_spend,
                case_ids=body.get("case_ids"),
                compare_id=compare_id,
            )
            _finish_compare_job(state, compare_id, result)
        except CompareError as exc:
            _fail_compare_job(state, compare_id, message=exc.message, hint=exc.hint)
        except Exception as exc:  # noqa: BLE001
            _fail_compare_job(state, compare_id, message=str(exc))

    threading.Thread(target=worker, name=f"skillgate-compare-{compare_id}", daemon=True).start()
    return {"compare_id": compare_id, "status": "running"}


def _start_versions_compare(state: AppState, body: dict[str, Any]) -> dict[str, Any]:
    load_env(state.root)
    skill_raw = str(body.get("skill") or "").strip()
    if not skill_raw:
        fail(400, "Pick a skill first.")
    path = find_skill(state.root, skill_raw)
    run_ids = body.get("run_ids")
    git_refs = body.get("git_refs")
    compare_id = uuid.uuid4().hex[:12]
    if state.gate_busy():
        fail(409, "A check or compare is already running.")

    def worker() -> None:
        try:
            result = run_versions_compare(
                path,
                run_ids=run_ids if isinstance(run_ids, list) else None,
                git_refs=git_refs if isinstance(git_refs, list) else None,
                root=state.root,
                rerun=bool(body.get("rerun")),
                compare_id=compare_id,
            )
            _finish_compare_job(state, compare_id, result)
        except CompareError as exc:
            _fail_compare_job(state, compare_id, message=exc.message, hint=exc.hint)
        except Exception as exc:  # noqa: BLE001
            _fail_compare_job(state, compare_id, message=str(exc))

    with state.lock:
        state.compares[compare_id] = {"compare_id": compare_id, "status": "running", "mode": "versions"}
    threading.Thread(target=worker, name=f"skillgate-compare-{compare_id}", daemon=True).start()
    return {"compare_id": compare_id, "status": "running"}
