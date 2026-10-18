"""Jev adapter. Built-in questions and the case's extra questions."""

from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlparse

from skillgate_ai.judge_openai import (
    DEFAULT_TIMEOUT_SEC,
    _answers_from_decisions_list,
    _normalize_answers,
    _path_is_recorded,
    _state_text,
)
from skillgate_ai.judge_spec import builtin_spec, spec_decisions_questions
from skillgate_ai.openai_http import PostFn, post_openai_json

DISPLAY_NAME = "the judge"
OPENROUTER_DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"


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
        resolved = spec if spec is not None else builtin_spec()
        result = post_openai_json(
            _score_url(self.base_url),
            api_key=self.api_key,
            payload=_request_body(
                self.base_url,
                model=self.model,
                text=_state_text(state),
                questions=spec_decisions_questions(resolved, include_path=include_path),
            ),
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
            who=DISPLAY_NAME,
        )
        if result.get("status") != "ok":
            return {**result, "reason": _public_failure(result)}
        data = result["data"]
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        answers = _normalize_answers(
            _answers_from_decisions_list(data),
            include_path=include_path,
            spec=resolved,
        )
        return {
            "status": "completed",
            "model": str(data.get("model") or self.model),
            "answers": answers,
            "usage": usage,
            "warnings": [],
        }

    def ping(self, *, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
        result = post_openai_json(
            _score_url(self.base_url),
            api_key=self.api_key,
            payload=_request_body(
                self.base_url,
                model=self.model,
                text="ping",
                questions=[
                    {
                        "type": "predicate",
                        "name": "connection_test",
                        "instructions": "Is this a connection test?",
                    }
                ],
            ),
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
            retries=False,
            who=DISPLAY_NAME,
        )
        if result.get("status") == "ok":
            return {"ok": True, "message": "Connected to the judge."}
        return {"ok": False, "message": _public_failure(result)}


def _score_levels(levels: Any) -> list[str]:
    if not isinstance(levels, list):
        return []
    labels: list[str] = []
    for level in levels:
        if isinstance(level, Mapping):
            label = str(level.get("label") or level.get("value") or "").strip()
        else:
            label = str(level or "").strip()
        if label:
            labels.append(label)
    return labels


def _openrouter_host(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").lower()
    return host == "openrouter.ai" or host.endswith(".openrouter.ai")


def _score_url(base_url: str) -> str:
    """OpenRouter serves Jev at its Decisions API. Other bases keep /evaluate."""
    if _openrouter_host(base_url):
        return OPENROUTER_DECISIONS_URL
    base = base_url.rstrip("/")
    if base.endswith("/evaluate") or base.endswith("/decisions"):
        return base
    return f"{base}/evaluate"


def _request_body(
    base_url: str,
    *,
    model: str,
    text: str,
    questions: list[dict[str, Any]],
) -> dict[str, Any]:
    if _openrouter_host(base_url):
        return {
            "model": model,
            "state": text,
            "questions": _openrouter_questions(questions),
        }
    return {"model": model, "input": text, "questions": questions}


def _openrouter_questions(questions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Map Skill Gate's question list onto OpenRouter's keyed Decisions schema."""
    mapped: dict[str, dict[str, Any]] = {}
    for question in questions:
        name = str(question.get("name") or "").strip()
        if not name:
            continue
        instructions = str(question.get("instructions") or name)
        criteria: dict[str, str] = {}
        choices = question.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, Mapping):
                    continue
                value = str(choice.get("value") or "").strip()
                if not value:
                    continue
                description = choice.get("description")
                criteria[value] = (
                    description.strip()
                    if isinstance(description, str) and description.strip()
                    else value
                )
        if criteria:
            mapped[name] = {
                "type": "choice",
                "instructions": instructions,
                "criteria": criteria,
            }
            continue
        if str(question.get("type") or "") == "score" or question.get("levels"):
            levels = _score_levels(question.get("levels"))
            mapped[name] = {
                "type": "score",
                "instructions": instructions,
                "criteria": levels or ["1", "2", "3", "4", "5"],
            }
            continue
        mapped[name] = {
            "type": "noul",
            "instructions": instructions,
            "criteria": {
                "true": "Yes. The instructions are satisfied.",
                "false": "No. The instructions are not satisfied.",
            },
        }
    return mapped


def _public_failure(result: Mapping[str, Any]) -> str:
    """Say what failed. Never name a scoring provider."""
    status = result.get("http_status")
    reason = str(result.get("reason") or "")
    if status == 404:
        return "No scoring endpoint at this URL."
    if status == 401:
        return "This API key was not accepted."
    if status == 403:
        return "This API key is not allowed to score."
    if status in {402, 429} and "out of credits" in reason.lower():
        return "This account is out of credits."
    if status == 429:
        return "This request was rate-limited. Wait and retry, or check billing."
    if status == 400:
        return "This scoring request was rejected."
    if isinstance(status, int):
        return f"Scoring failed (HTTP {status})."
    return "Could not connect."


