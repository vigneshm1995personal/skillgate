"""OpenAI-compatible adapter: /decisions first, then structured JSON."""

from __future__ import annotations

from typing import Any, Mapping

from skillgate_ai.judge_openai import (
    DEFAULT_TIMEOUT_SEC,
    DecisionsBackend,
    StructuredOutputsBackend,
)
from skillgate_ai.judge_spec import JudgeSpec, builtin_spec
from skillgate_ai.openai_http import PostFn, post_openai_json

DISPLAY_NAME = "Other"


def _missing_scoring_endpoint(result: Mapping[str, Any]) -> bool:
    if int(result.get("http_status") or 0) == 404:
        return True
    reason = str(result.get("reason") or "").lower()
    return "no scoring endpoint" in reason or "no matching endpoint" in reason


class CompatibleBackend:
    name = "compatible"
    supports_why = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str = "gpt-6-luna",
        decisions_path: str = "/decisions",
        post: PostFn | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.decisions_path = decisions_path if decisions_path.startswith("/") else f"/{decisions_path}"
        self._post = post
        self._decisions = DecisionsBackend(
            api_key=api_key,
            base_url=self.base_url,
            model=model,
            post=post,
            who=DISPLAY_NAME,
            decisions_path=self.decisions_path,
        )
        self._structured = StructuredOutputsBackend(
            api_key=api_key,
            base_url=self.base_url,
            model=model,
            post=post,
            who=DISPLAY_NAME,
        )
        self.supports_confidence = True
        self.who = DISPLAY_NAME

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
        spec: JudgeSpec | None = None,
    ) -> dict[str, Any]:
        resolved = spec or builtin_spec()
        first = self._decisions.evaluate(
            state=state, images=images, timeout_sec=timeout_sec, spec=resolved
        )
        if first.get("status") == "completed":
            self.supports_confidence = True
            first["scoring_endpoint"] = "decisions"
            self.scoring_endpoint = "decisions"
            return first
        if _missing_scoring_endpoint(first):
            self.supports_confidence = False
            fallback = self._structured.evaluate(
                state=state, images=images, timeout_sec=timeout_sec, spec=resolved
            )
            if fallback.get("status") == "completed":
                fallback["scoring_endpoint"] = "responses"
                self.scoring_endpoint = "responses"
                return fallback
            return {
                "status": "error",
                "reason": "This endpoint did not accept scoring requests. Check the base URL.",
                "model": self.model,
            }
        return first

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_sec: float,
        retries: bool = True,
    ) -> dict[str, Any]:
        return self._structured.post_json(
            path, payload, timeout_sec=timeout_sec, retries=retries
        )

    def ping(self, *, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
        result = post_openai_json(
            f"{self.base_url}{self.decisions_path}",
            api_key=self.api_key,
            payload={
                "model": self.model,
                "input": "ping",
                "questions": [
                    {
                        "type": "predicate",
                        "name": "connection_test",
                        "instructions": "Is this a connection test?",
                    }
                ],
            },
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
            retries=False,
            who=DISPLAY_NAME,
        )
        if result.get("status") == "ok":
            self.scoring_endpoint = "decisions"
            return {
                "ok": True,
                "message": f"Connected to {DISPLAY_NAME} via the Decisions API.",
                "scoring_endpoint": "decisions",
            }
        if _missing_scoring_endpoint(result):
            fallback = self._structured.post_json(
                "/responses",
                {"model": self.model, "input": "ping"},
                timeout_sec=timeout_sec,
                retries=False,
            )
            if fallback.get("status") == "ok":
                self.scoring_endpoint = "responses"
                return {
                    "ok": True,
                    "message": f"Connected to {DISPLAY_NAME} via the Responses API.",
                    "scoring_endpoint": "responses",
                }
            return {
                "ok": False,
                "message": "This endpoint did not accept scoring requests. Check the base URL.",
            }
        reason = str(result.get("reason") or "Could not connect.")
        reason = reason.replace("OpenAI", DISPLAY_NAME).replace("the judge", DISPLAY_NAME)
        return {"ok": False, "message": reason}


