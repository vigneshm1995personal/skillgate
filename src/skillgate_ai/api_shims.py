"""Hosted-app route shims. Hidden in local UI; kept so the same React app does not 404."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

from skillgate_ai.api_payloads import fail, skill_payload, state_of
from skillgate_ai.catalog import find_skill


def register_hosted_shims(app: FastAPI) -> None:
    @app.get("/api/auth/me")
    def auth_me() -> dict[str, Any]:
        return {"auth_required": False, "user": None}

    @app.post("/api/auth/signout")
    def auth_signout() -> dict[str, Any]:
        return {}

    @app.get("/api/analytics")
    def analytics(request: Request, skill: str | None = None) -> dict[str, Any]:
        del skill
        state_of(request)
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

    @app.post("/api/evals/promote-draft")
    async def promote_draft(request: Request) -> dict[str, Any]:
        state = state_of(request)
        body = await request.json()
        task = body.get("task") or {}
        skill_name = body.get("skill")
        skill = None
        if skill_name:
            skill = skill_payload(state, find_skill(state.root, str(skill_name)))
        check = {
            "id": str(task.get("id") or "draft"),
            "prompt": str(task.get("prompt") or ""),
            "should_trigger": True,
            "files": task.get("files") or [],
        }
        return {"check": check, "hints": [], "source_task_id": task.get("id"), "skill": skill}

    @app.post("/api/evals/suggest-skill-updates")
    def suggest_updates() -> None:
        fail(404, "Suggest skill updates isn’t in the local app.")
