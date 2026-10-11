"""Judge protocol. Default is skip — deterministic scorers own red/green."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from skillgate_ai.config import LLMConfig
from skillgate_ai.errors import MissingLLMKeyError
from skillgate_ai.harness import is_live_harness


class Judge(Protocol):
    """Optional outcome judge. Private hosted injects TypeSafe outside this repo."""

    def judge(
        self,
        goal: str,
        artifacts: list[dict[str, Any]],
        transcript_tail: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Return ``{passed, cells, ...}``. Skip implementations set ``status=skip``."""
        ...

    def explain_fail(
        self,
        reasons: list[str],
        *,
        judged: Mapping[str, Any] | None = None,
        check: str = "",
        transcript_tail: str = "",
        expected_output: Any = None,
        actual_output: Any = None,
    ) -> str | None:
        """One Fail sentence after the engine gate. Skip returns None."""
        ...


class SkipJudge:
    """Det-only default. Does not change the scorer AND verdict."""

    name = "skip"

    def judge(
        self,
        goal: str,
        artifacts: list[dict[str, Any]],
        transcript_tail: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        del goal, artifacts, transcript_tail, kwargs
        return {
            "status": "skip",
            "passed": None,
            "cells": [],
            "provider": "skip",
            "backend": "skip",
            "display_name": "Checks",
            "reason": "Checks scored this run.",
        }

    def explain_fail(
        self,
        reasons: list[str],
        *,
        judged: Mapping[str, Any] | None = None,
        check: str = "",
        transcript_tail: str = "",
        expected_output: Any = None,
        actual_output: Any = None,
    ) -> str | None:
        del reasons, judged, check, transcript_tail, expected_output, actual_output
        return None


def default_judge() -> SkipJudge:
    return SkipJudge()


def missing_openai_judge_key() -> MissingLLMKeyError:
    return MissingLLMKeyError(
        "No OpenAI API key found. Scoring with OpenAI needs your key.",
        hint="Add an OpenAI key in Settings (`skillgate keys set`), or set SKILLGATE_JUDGE=skip.",
    )


def _judge_api_key(cfg: LLMConfig) -> str:
    return (cfg.openai_api_key or cfg.gateway_api_key or "").strip()


def resolve_judge(cfg: LLMConfig, *, harness_name: str) -> Judge:
    """Pick Skip vs OpenAI. Demo / non-live always skip."""
    pref = (cfg.judge_pref or "auto").strip().lower() or "auto"
    if pref == "skip" or not is_live_harness(harness_name):
        return SkipJudge()
    key = _judge_api_key(cfg)
    if pref == "openai":
        if not key:
            raise missing_openai_judge_key()
        return _openai_judge(cfg)
    if key:
        return _openai_judge(cfg)
    return SkipJudge()


def _openai_judge(cfg: LLMConfig) -> Judge:
    from skillgate_ai.config import DEFAULT_JUDGE_MODEL
    from skillgate_ai.judge_openai import (
        DEFAULT_BASE_URL,
        DISPLAY_NAME,
        GATEWAY_DECISIONS_MODEL,
        GATEWAY_DISPLAY_NAME,
        make_openai_judge,
    )

    api_key = (cfg.openai_api_key or "").strip()
    backend = cfg.judge_backend
    model = cfg.judge_model
    base_url = DEFAULT_BASE_URL
    display_name = DISPLAY_NAME
    if not api_key:
        api_key = (cfg.gateway_api_key or "").strip()
        base_url = (cfg.gateway_base_url or "").rstrip("/") or DEFAULT_BASE_URL
        display_name = GATEWAY_DISPLAY_NAME
        backend_name = (backend or "decisions").strip().lower()
        if backend_name not in {"structured", "responses"} and (model or "").strip() in {
            "",
            DEFAULT_JUDGE_MODEL,
        }:
            model = GATEWAY_DECISIONS_MODEL
    return make_openai_judge(
        api_key=api_key,
        backend=backend,
        model=model,
        min_confidence=cfg.judge_min_confidence,
        why_enabled=cfg.judge_why,
        reasoning_effort=cfg.judge_reasoning_effort,
        timeout_sec=cfg.judge_timeout_sec,
        base_url=base_url,
        display_name=display_name,
    )


def judge_stamp(judge: Judge | None) -> dict[str, str]:
    if judge is None or isinstance(judge, SkipJudge) or getattr(judge, "name", "") == "skip":
        return {
            "provider": "skip",
            "backend": "skip",
            "display_name": "Checks",
        }
    from skillgate_ai.judge_openai import DISPLAY_NAME, OutcomeJudge

    if isinstance(judge, OutcomeJudge):
        return {
            "provider": "openai",
            "backend": judge.backend.name,
            "display_name": getattr(judge, "display_name", None) or DISPLAY_NAME,
            "model": str(getattr(judge.backend, "model", "") or judge.model or ""),
        }
    backend_obj = getattr(judge, "backend", None)
    backend = getattr(backend_obj, "name", None) or getattr(judge, "name", "openai")
    model = getattr(backend_obj, "model", None) or getattr(judge, "model", "") or ""
    return {
        "provider": "openai",
        "backend": str(backend),
        "display_name": str(getattr(judge, "display_name", None) or DISPLAY_NAME),
        "model": str(model),
    }
