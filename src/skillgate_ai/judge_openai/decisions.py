"""Direct-answer scoring. Chat and Responses completion models are refused."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from skillgate_ai.judge_bank import (
    DEFAULT_MIN_CONFIDENCE,
)
from skillgate_ai.judge_context import attach_adherence_context, attach_tool_check_evidence
from skillgate_ai.judge_openai.backend import (
    DEFAULT_MODEL,
    DEFAULT_TIMEOUT_SEC,
    DISPLAY_NAME,
    JudgeBackend,
    _decisions_model,
    _OpenAIPosted,
)
from skillgate_ai.judge_openai.outcome import OutcomeJudge
from skillgate_ai.judge_openai.payload import (
    _annotate_payload_too_large,
    _answers_from_decisions_list,
    _finished_answers,
    _normalize_answers,
    _path_is_recorded,
    _state_text,
    _user_content,
)
from skillgate_ai.judge_spec import (
    JudgeSpec,
    builtin_spec,
    spec_decisions_questions,
)
from skillgate_ai.openai_http import (
    DEFAULT_BASE_URL,
    PostFn,
)


class DecisionsBackend(_OpenAIPosted):
    name = "decisions"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        post: PostFn | None = None,
        who: str = DISPLAY_NAME,
        decisions_path: str = "/decisions",
    ) -> None:
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=_decisions_model(model),
            post=post,
            who=who,
        )
        path = (decisions_path or "/decisions").strip() or "/decisions"
        self.decisions_path = path if path.startswith("/") else f"/{path}"

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
        spec: JudgeSpec | None = None,
    ) -> dict[str, Any]:
        text = _state_text(state)
        content = _user_content(text, images)
        payload_input: str | list[dict[str, Any]]
        if images:  # noqa: SIM108
            payload_input = [{"role": "user", "content": content}]
        else:
            payload_input = text
        include_path = _path_is_recorded(state.get("path"))
        resolved = spec or builtin_spec()
        result = self.post_json(
            self.decisions_path,
            {
                "model": self.model,
                "input": payload_input,
                "questions": attach_tool_check_evidence(
                    attach_adherence_context(
                        spec_decisions_questions(resolved, include_path=include_path),
                        state,
                    ),
                    state,
                ),
            },
            timeout_sec=timeout_sec,
        )
        if result.get("status") != "ok":
            return _annotate_payload_too_large(result, state)
        data = result["data"]
        from skillgate_ai.usage import normalize_judge_api_usage

        model_name = str(data.get("model") or self.model)
        usage = normalize_judge_api_usage(data, model=model_name)
        finished = _finished_answers(
            _normalize_answers(
                _answers_from_decisions_list(data),
                include_path=include_path,
                spec=resolved,
            ),
            model=model_name,
            usage=usage,
        )
        finished["scoring_endpoint"] = "decisions"
        return finished

    def ping(self, *, timeout_sec: float = DEFAULT_TIMEOUT_SEC) -> dict[str, Any]:
        result = self.post_json(
            self.decisions_path,
            {
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
            retries=False,
        )
        if result.get("status") == "ok":
            return {
                "ok": True,
                "message": "Connected to the judge.",
                "scoring_endpoint": "decisions",
            }
        return {"ok": False, "message": str(result.get("reason") or "Could not connect.")}


def ping_openai_backend(
    backend: JudgeBackend, *, display_name: str = DISPLAY_NAME
) -> dict[str, Any]:
    del display_name
    result = backend.post_json(
        "/decisions",
        {
            "model": backend.model,
            "input": "ping",
            "questions": [
                {
                    "type": "predicate",
                    "name": "connection_test",
                    "instructions": "Is this a connection test?",
                }
            ],
        },
        timeout_sec=DEFAULT_TIMEOUT_SEC,
        retries=False,
    )
    if result.get("status") == "ok":
        return {
            "ok": True,
            "message": "Connected to the judge.",
            "scoring_endpoint": "decisions",
        }
    payload = {"ok": False, "message": str(result.get("reason") or "Could not connect.")}
    upstream = result.get("upstream")
    if isinstance(upstream, str) and upstream.strip():
        payload["upstream"] = upstream.strip()
    return payload


def make_openai_judge(
    *,
    api_key: str,
    backend: str = "decisions",
    model: str = DEFAULT_MODEL,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    why_enabled: bool = True,
    reasoning_effort: str = "low",
    timeout_sec: float = DEFAULT_TIMEOUT_SEC,
    base_url: str = DEFAULT_BASE_URL,
    post: PostFn | None = None,
    display_name: str = DISPLAY_NAME,
    chosen: bool = False,
) -> OutcomeJudge:
    from skillgate_ai.errors import SkillGateError

    del why_enabled
    name = (backend or "decisions").strip().lower()
    if name in {"structured", "responses", "chat", "completions"}:
        from skillgate_ai.judge_providers.decision import CHAT_NOT_A_JUDGE

        raise SkillGateError(CHAT_NOT_A_JUDGE, exit_code=2)
    impl = DecisionsBackend(
        api_key=api_key,
        base_url=base_url,
        model=model,
        post=post,
        who=display_name,
    )
    return OutcomeJudge(
        impl,
        min_confidence=min_confidence,
        why_enabled=False,
        reasoning_effort=reasoning_effort,
        timeout_sec=timeout_sec,
        display_name=display_name,
        provider="openai",
        chosen=chosen,
        supports_why=False,
        supports_confidence=True,
    )
