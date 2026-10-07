"""Judge protocol. Default is skip — deterministic scorers own red/green."""

from __future__ import annotations

from typing import Any, Protocol

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
            "display_name": "Built-in checker",
            "reason": "SkipJudge: deterministic scorers own this check.",
        }


def default_judge() -> SkipJudge:
    return SkipJudge()


def missing_openai_judge_key() -> MissingLLMKeyError:
    return MissingLLMKeyError(
        "No OpenAI API key found. Scoring with OpenAI needs your key.",
        hint="Add OPENAI_API_KEY in .env, or skip scoring and use the built-in checker.",
    )


def resolve_judge(cfg: LLMConfig, *, harness_name: str) -> Judge:
    """Pick Skip vs OpenAI. Demo / non-live always skip."""
    pref = (cfg.judge_pref or "auto").strip().lower() or "auto"
    if pref == "skip" or not is_live_harness(harness_name):
        return SkipJudge()
    if pref == "openai":
        if not cfg.openai_api_key:
            raise missing_openai_judge_key()
        return _openai_judge(cfg)
    if cfg.openai_api_key:
        return _openai_judge(cfg)
    return SkipJudge()


def _openai_judge(cfg: LLMConfig) -> Judge:
    from skillgate_ai.judge_openai import DEFAULT_BASE_URL, make_openai_judge

    return make_openai_judge(
        api_key=cfg.openai_api_key or "",
        backend=cfg.judge_backend,
        model=cfg.judge_model,
        min_confidence=cfg.judge_min_confidence,
        why_enabled=cfg.judge_why,
        reasoning_effort=cfg.judge_reasoning_effort,
        timeout_sec=cfg.judge_timeout_sec,
        base_url=DEFAULT_BASE_URL,
    )


def judge_stamp(judge: Judge | None) -> dict[str, str]:
    if judge is None or isinstance(judge, SkipJudge) or getattr(judge, "name", "") == "skip":
        return {
            "provider": "skip",
            "backend": "skip",
            "display_name": "Built-in checker",
        }
    backend = getattr(getattr(judge, "backend", None), "name", None) or getattr(
        judge, "name", "openai"
    )
    model = getattr(judge, "model", "") or ""
    return {
        "provider": "openai",
        "backend": str(backend),
        "display_name": "OpenAI (your key)",
        "model": str(model),
    }
