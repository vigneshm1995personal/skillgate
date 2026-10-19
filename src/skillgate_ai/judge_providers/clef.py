"""Decision-model adapter. Posts the decision payload to the account endpoint."""

from __future__ import annotations

import re
from typing import Any, Mapping

from skillgate_ai.errors import SkillGateError
from skillgate_ai.judge_openai import (
    DEFAULT_TIMEOUT_SEC,
    _answers_from_decisions_list,
    _normalize_answers,
    _path_is_recorded,
    _state_text,
)
from skillgate_ai.judge_providers.jev import _openrouter_questions
from skillgate_ai.judge_spec import builtin_spec, spec_decisions_questions
from skillgate_ai.openai_http import PostFn, post_openai_json

DISPLAY_NAME = "the judge"
_ACCOUNT_ID = re.compile(r"^[A-Za-z0-9]+$")
_WORKERS_AI = "https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/cloudflare/{model}"


class ClefBackend:
    name = "clef"
    supports_confidence = False
    supports_why = False

    def __init__(
        self,
        *,
        api_key: str,
        account_id: str,
        model: str = "clef",
        post: PostFn | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key
        self.account_id = _require_account(account_id)
        self.model = _model_slug(model)
        self._post = post
        self.base_url = (base_url or "").strip() or None

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
        questions = spec_decisions_questions(resolved, include_path=include_path)
        result = post_openai_json(
            self._url(),
            api_key=self.api_key,
            payload={
                "model": self.model,
                "state": _state_text(state),
                "questions": _openrouter_questions(questions),
            },
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
            who=DISPLAY_NAME,
        )
        if result.get("status") != "ok":
            return result
        data = _unwrap(result["data"])
        if data is None:
            return {
                "status": "error",
                "reason": "The judge couldn't score this check.",
                "model": self.model,
            }
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
            self._url(),
            api_key=self.api_key,
            payload={
                "model": self.model,
                "state": "ping",
                "questions": _openrouter_questions(
                    [
                        {
                            "type": "predicate",
                            "name": "connection_test",
                            "instructions": "Is this a connection test?",
                        }
                    ]
                ),
            },
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
            retries=False,
            who=DISPLAY_NAME,
        )
        if result.get("status") == "ok":
            return {"ok": True, "message": "Connected to the judge."}
        return {
            "ok": False,
            "message": str(result.get("reason") or "The judge couldn't score this check."),
        }

    def _url(self) -> str:
        if self.base_url:
            return self.base_url
        return _WORKERS_AI.format(account_id=self.account_id, model=self.model)


def _require_account(account_id: str) -> str:
    account = (account_id or "").strip()
    if not account or not _ACCOUNT_ID.fullmatch(account):
        from skillgate_ai.judge_providers.decision import NEEDS_ACCOUNT

        raise SkillGateError(NEEDS_ACCOUNT, exit_code=2)
    return account


def _model_slug(model: str) -> str:
    from skillgate_ai.judge_setup import resolve_model

    return resolve_model("clef", (model or "").strip() or "clef")


def _unwrap(data: Any) -> Mapping[str, Any] | None:
    if not isinstance(data, Mapping):
        return None
    if data.get("success") is False:
        return None
    result = data.get("result")
    if isinstance(result, Mapping):
        return result
    return data
