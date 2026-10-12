"""Judge protocol. Default is skip — deterministic scorers own red/green."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from skillgate_ai.config import LLMConfig
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.harness import is_live_harness
from skillgate_ai.judge_copy import CHOSEN_LABELS, DEFAULT_NAME


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


def missing_provider_key(provider: str) -> MissingLLMKeyError:
    labels = {
        "openai": "OpenAI",
        "jev": "Jev",
        "aws": "AWS",
        "compatible": "Other",
    }
    label = labels.get(provider, "scoring")
    return MissingLLMKeyError(
        f"Add your {label} key in Settings (`skillgate keys set`), or pick a different scoring provider.",
        exit_code=2,
    )


def _judge_api_key(cfg: LLMConfig) -> str:
    return (cfg.openai_api_key or cfg.gateway_api_key or "").strip()


def _display_name(provider: str, *, chosen: bool) -> str:
    if chosen:
        return CHOSEN_LABELS.get(provider, DEFAULT_NAME)
    return DEFAULT_NAME


def resolve_judge(cfg: LLMConfig, *, harness_name: str) -> Judge:
    """Pick Skip vs a scoring adapter. Demo / non-live always skip."""
    pref = (cfg.judge_pref or "auto").strip().lower() or "auto"
    if pref == "skip" or not is_live_harness(harness_name):
        return SkipJudge()
    selected = (getattr(cfg, "judge_provider", None) or "auto").strip().lower() or "auto"
    chosen = bool(getattr(cfg, "judge_chosen", False)) and selected in CHOSEN_LABELS
    if pref == "openai":
        if not _judge_api_key(cfg):
            raise missing_openai_judge_key()
        return _openai_judge(cfg, chosen=chosen and selected == "openai")
    if selected in CHOSEN_LABELS and selected != "openai":
        return _provider_judge(cfg, selected, chosen=True)
    if selected == "openai":
        if not _judge_api_key(cfg):
            raise missing_provider_key("openai")
        return _openai_judge(cfg, chosen=True)
    key = _judge_api_key(cfg)
    if key:
        return _openai_judge(cfg, chosen=False)
    return SkipJudge()


def _openai_judge(cfg: LLMConfig, *, chosen: bool) -> Judge:
    from skillgate_ai.config import DEFAULT_JUDGE_MODEL
    from skillgate_ai.judge_openai import (
        DEFAULT_BASE_URL,
        GATEWAY_DECISIONS_MODEL,
        make_openai_judge,
    )

    api_key = (cfg.openai_api_key or "").strip()
    backend = cfg.judge_backend
    model = cfg.judge_model
    base_url = DEFAULT_BASE_URL
    display_name = _display_name("openai", chosen=chosen)
    if not api_key:
        api_key = (cfg.gateway_api_key or "").strip()
        base_url = (cfg.gateway_base_url or "").rstrip("/") or DEFAULT_BASE_URL
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
        chosen=chosen,
    )


def _provider_judge(cfg: LLMConfig, provider: str, *, chosen: bool) -> Judge:
    from skillgate_ai.judge_openai import OutcomeJudge

    display = _display_name(provider, chosen=chosen)
    if provider == "jev":
        key = (getattr(cfg, "jev_api_key", None) or "").strip()
        base_url = (getattr(cfg, "judge_endpoint", None) or "").strip()
        if not key:
            raise missing_provider_key("jev")
        if not base_url:
            raise SkillGateError("Jev scoring needs a base URL in Settings.", exit_code=2)
        from skillgate_ai.judge_providers.jev import JevBackend

        backend = JevBackend(api_key=key, base_url=base_url)
        return OutcomeJudge(
            backend,
            min_confidence=cfg.judge_min_confidence,
            why_enabled=False,
            timeout_sec=cfg.judge_timeout_sec,
            display_name=display,
            provider="jev",
            chosen=chosen,
            supports_why=False,
            supports_confidence=False,
        )
    if provider == "aws":
        access = (getattr(cfg, "aws_access_key_id", None) or "").strip()
        secret = (getattr(cfg, "aws_secret_access_key", None) or "").strip()
        region = (getattr(cfg, "judge_region", None) or "").strip()
        model = (getattr(cfg, "judge_provider_model", None) or "").strip()
        if not access or not secret:
            raise missing_provider_key("aws")
        if not region:
            raise SkillGateError("AWS scoring needs a region in Settings.", exit_code=2)
        if not model:
            raise SkillGateError("AWS scoring needs a model in Settings.", exit_code=2)
        from skillgate_ai.judge_providers.aws import AwsBackend

        backend = AwsBackend(
            access_key=access,
            secret_key=secret,
            region=region,
            model=model,
            session_token=(getattr(cfg, "aws_session_token", None) or "").strip() or None,
        )
        return OutcomeJudge(
            backend,
            min_confidence=cfg.judge_min_confidence,
            why_enabled=cfg.judge_why,
            timeout_sec=cfg.judge_timeout_sec,
            display_name=display,
            provider="aws",
            chosen=chosen,
            supports_why=True,
            supports_confidence=False,
        )
    key = (cfg.gateway_api_key or "").strip()
    base_url = (getattr(cfg, "judge_endpoint", None) or cfg.gateway_base_url or "").strip()
    if not key:
        raise missing_provider_key("compatible")
    if not base_url:
        raise SkillGateError("Other scoring needs a base URL in Settings.", exit_code=2)
    from skillgate_ai.judge_providers.compatible import CompatibleBackend

    backend = CompatibleBackend(
        api_key=key,
        base_url=base_url,
        model=(getattr(cfg, "judge_provider_model", None) or cfg.judge_model),
        decisions_path=getattr(cfg, "judge_decisions_path", None) or "/decisions",
    )
    return OutcomeJudge(
        backend,
        min_confidence=cfg.judge_min_confidence,
        why_enabled=cfg.judge_why,
        timeout_sec=cfg.judge_timeout_sec,
        display_name=display,
        provider="compatible",
        chosen=chosen,
        supports_why=True,
        supports_confidence=True,
    )


def ping_judge(cfg: LLMConfig) -> dict[str, str | bool]:
    judge = resolve_judge(cfg, harness_name="llm")
    if isinstance(judge, SkipJudge):
        return {"ok": False, "message": "No scoring provider — file checks only."}
    backend = getattr(judge, "backend", None)
    display = str(getattr(judge, "display_name", None) or DEFAULT_NAME)
    if backend is not None and hasattr(backend, "ping"):
        result = backend.ping()
        if isinstance(result, dict):
            return {"ok": bool(result.get("ok")), "message": str(result.get("message") or "")}
    from skillgate_ai.judge_openai import ping_openai_backend

    if backend is not None and hasattr(backend, "post_json"):
        return ping_openai_backend(backend, display_name=display)
    return {"ok": False, "message": "This scoring provider cannot be tested."}


def judge_stamp(judge: Judge | None) -> dict[str, str]:
    if judge is None or isinstance(judge, SkipJudge) or getattr(judge, "name", "") == "skip":
        return {
            "provider": "skip",
            "backend": "skip",
            "display_name": "Checks",
            "chosen": False,
        }
    from skillgate_ai.judge_openai import OutcomeJudge

    chosen = bool(getattr(judge, "chosen", False))
    if isinstance(judge, OutcomeJudge):
        return {
            "provider": str(judge.name or "openai"),
            "backend": judge.backend.name,
            "display_name": str(getattr(judge, "display_name", None) or DEFAULT_NAME),
            "model": str(getattr(judge.backend, "model", "") or judge.model or ""),
            "chosen": chosen,
        }
    backend_obj = getattr(judge, "backend", None)
    backend = getattr(backend_obj, "name", None) or getattr(judge, "name", "openai")
    model = getattr(backend_obj, "model", None) or getattr(judge, "model", "") or ""
    return {
        "provider": str(getattr(judge, "name", None) or "openai"),
        "backend": str(backend),
        "display_name": str(getattr(judge, "display_name", None) or DEFAULT_NAME),
        "model": str(model),
        "chosen": chosen,
    }
