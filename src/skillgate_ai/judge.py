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
            "display_name": "Built-in checker",
            "reason": "Built-in checker owns this check.",
        }

    def explain_fail(
        self,
        reasons: list[str],
        *,
        judged: Mapping[str, Any] | None = None,
        check: str = "",
        transcript_tail: str = "",
    ) -> str | None:
        del reasons, judged, check, transcript_tail
        return None


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
    from skillgate_ai.judge_openai import DISPLAY_NAME, OutcomeJudge

    if isinstance(judge, OutcomeJudge):
        return {
            "provider": "openai",
            "backend": judge.backend.name,
            "display_name": DISPLAY_NAME,
            "model": str(getattr(judge.backend, "model", "") or judge.model or ""),
        }
    backend_obj = getattr(judge, "backend", None)
    backend = getattr(backend_obj, "name", None) or getattr(judge, "name", "openai")
    model = getattr(backend_obj, "model", None) or getattr(judge, "model", "") or ""
    return {
        "provider": "openai",
        "backend": str(backend),
        "display_name": DISPLAY_NAME,
        "model": str(model),
    }
