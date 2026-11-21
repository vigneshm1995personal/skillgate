"""Direct-answer scoring. Chat and Responses completion models are refused."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from skillgate_ai.judge_spec import (
    JudgeSpec,
)
from skillgate_ai.openai_http import (
    DEFAULT_BASE_URL,
    PostFn,
    post_openai_json,
)

DEFAULT_MODEL = "gpt-6-luna"

GATEWAY_DECISIONS_MODEL = "openai/gpt-6-luna-decisions"

DEFAULT_TIMEOUT_SEC = 20.0

WHY_TIMEOUT_SEC = 10.0

WHY_MAX_OUTPUT_TOKENS = 128

WHY_OUTPUT_CHARS = 1500

TRANSCRIPT_TAIL_CHARS = 4000

DISPLAY_NAME = "the judge"

GATEWAY_DISPLAY_NAME = "the judge"

CHOSEN_DISPLAY_NAME = DISPLAY_NAME


def _decisions_model(model: str) -> str:
    slug = (model or "").strip() or DEFAULT_MODEL
    if slug == DEFAULT_MODEL or slug.endswith("-decisions"):
        return slug
    return DEFAULT_MODEL


class JudgeBackend(Protocol):
    """HTTP client for one decisions endpoint. A judge implements DecisionModel."""

    name: str
    model: str
    api_key: str

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        images: list[dict[str, str]],
        timeout_sec: float,
        spec: JudgeSpec | None = None,
    ) -> dict[str, Any]:
        """Return status/model/answers. Never logs secrets."""
        ...

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_sec: float,
        retries: bool = True,
    ) -> dict[str, Any]:
        """POST JSON to this backend's OpenAI base URL."""
        ...


class _OpenAIPosted:
    """HTTP for one OpenAI key/base/model. Backends own evaluate; why uses post_json."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        post: PostFn | None = None,
        who: str = DISPLAY_NAME,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._post = post
        self.who = who or DISPLAY_NAME

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout_sec: float,
        retries: bool = True,
    ) -> dict[str, Any]:
        suffix = path if path.startswith("/") else f"/{path}"
        return post_openai_json(
            f"{self.base_url}{suffix}",
            api_key=self.api_key,
            payload=payload,
            timeout_sec=timeout_sec,
            model=self.model,
            post=self._post,
            retries=retries,
            who=self.who,
        )
