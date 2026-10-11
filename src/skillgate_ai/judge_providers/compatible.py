"""OpenAI-compatible adapter: /decisions first, then structured JSON."""

from __future__ import annotations

from typing import Any, Mapping

from skillgate_ai.judge_openai import (
    DEFAULT_TIMEOUT_SEC,
    DecisionsBackend,
    StructuredOutputsBackend,
    _path_is_recorded,
)
from skillgate_ai.judge_spec import JudgeSpec, builtin_spec
from skillgate_ai.openai_http import PostFn, post_openai_json

DISPLAY_NAME = "Other"


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
        include_path = _path_is_recorded(state.get("path"))
        first = self._decisions.evaluate(
            state=state, images=images, timeout_sec=timeout_sec, spec=resolved
        )
        if first.get("status") == "completed":
            self.supports_confidence = True
            return first
        if int(first.get("http_status") or 0) == 404 or "no scoring endpoint" in str(
            first.get("reason") or ""
        ).lower() or "no matching endpoint" in str(first.get("reason") or "").lower():
            self.supports_confidence = False
            fallback = self._structured.evaluate(
                state=state, images=images, timeout_sec=timeout_sec, spec=resolved
            )
            if fallback.get("status") == "completed":
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
        )
        if result.get("status") == "ok":
            return {"ok": True, "message": f"Connected to {DISPLAY_NAME}."}
        reason = str(result.get("reason") or "Could not connect.")
        reason = reason.replace("OpenAI", DISPLAY_NAME).replace("the judge", DISPLAY_NAME)
        return {"ok": False, "message": reason}


