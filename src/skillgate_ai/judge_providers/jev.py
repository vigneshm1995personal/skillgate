"""Jev adapter. Built-in six only; extras are skipped with a plain note."""

from __future__ import annotations

from typing import Any, Mapping

from skillgate_ai.judge_bank import decisions_questions
from skillgate_ai.judge_openai import (
    DEFAULT_TIMEOUT_SEC,
    _answers_from_decisions_list,
    _normalize_answers,
    _path_is_recorded,
    _state_text,
)
from skillgate_ai.openai_http import PostFn, post_openai_json

DISPLAY_NAME = "Jev"
JEV_EXTRAS_NOTE = (
    "Jev scores Skill Gate’s built-in questions only. Extra questions were skipped."
)


class JevBackend:
    name = "jev"
    supports_confidence = False
    supports_why = False

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        post: PostFn | None = None,
        model: str = "jev",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._post = post

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
        spec: Any = None,
    ) -> dict[str, Any]:
        del images
        include_path = _path_is_recorded(state.get("path"))
        extras = []
        if spec is not None:
            extras = [q.id for q in getattr(spec, "extras", ()) if not q.builtin]
        result = post_openai_json(
            f"{self.base_url}/evaluate",
            api_key=self.api_key,
            payload={
                "model": self.model,
                "input": _state_text(state),
                "questions": decisions_questions(include_path=include_path),
            },
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
            who=DISPLAY_NAME,
        )
        if result.get("status") != "ok":
            return {**result, "reason": _relabel(str(result.get("reason") or ""), DISPLAY_NAME)}
        data = result["data"]
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        answers = _normalize_answers(
            _answers_from_decisions_list(data),
            include_path=include_path,
        )
        warnings = [JEV_EXTRAS_NOTE] if extras else []
        return {
            "status": "completed",
            "model": str(data.get("model") or self.model),
            "answers": answers,
            "usage": usage,
            "warnings": warnings,
            "skipped": extras,
        }

    def ping(self, *, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
        result = post_openai_json(
            f"{self.base_url}/evaluate",
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
            return {"ok": True, "message": f"Connected to {DISPLAY_NAME}."}
        reason = _relabel(str(result.get("reason") or "Could not connect."), DISPLAY_NAME)
        return {"ok": False, "message": reason}


def _relabel(reason: str, who: str) -> str:
    return (
        reason.replace("OpenAI", who)
        .replace("the judge", who)
        .replace("The judge", who)
    )


