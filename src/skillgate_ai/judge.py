"""Judge protocol. Default is skip — deterministic scorers own red/green."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

from skillgate_ai.config import LLMConfig
from skillgate_ai.errors import MissingLLMKeyError, SkillGateError
from skillgate_ai.harness import is_live_harness
from skillgate_ai.judge_copy import DEFAULT_NAME


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
            "reason": "Quality scoring was skipped (no scoring key).",
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


def missing_decision_key() -> MissingLLMKeyError:
    from skillgate_ai.judge_providers.decision import NEEDS_KEY

    return MissingLLMKeyError(NEEDS_KEY, exit_code=2)


def missing_openai_judge_key() -> MissingLLMKeyError:
    return missing_decision_key()


def missing_provider_key(provider: str) -> MissingLLMKeyError:
    del provider
    return missing_decision_key()


def _display_name(provider: str, *, chosen: bool) -> str:
    del provider, chosen
    return DEFAULT_NAME


_builtins_ready = False


def ensure_builtin_decision_endpoints() -> None:
    """Register the built-in System 1 endpoints once."""
    global _builtins_ready
    if _builtins_ready:
        return
    from skillgate_ai.judge_providers.decision import DecisionEndpoint, register_decision_endpoint

    register_decision_endpoint(DecisionEndpoint("openai", _openai_from_cfg))
    register_decision_endpoint(DecisionEndpoint("jev", _jev_from_cfg))
    register_decision_endpoint(DecisionEndpoint("clef", _clef_from_cfg))
    _builtins_ready = True


def resolve_judge(cfg: LLMConfig, *, harness_name: str) -> Judge:
    """Pick file checks, or one registered decision model. Auto and non-live runs skip."""
    from skillgate_ai.judge_providers.decision import (
        CHAT_BACKENDS,
        CHAT_NOT_A_JUDGE,
        NOT_A_DECISION_MODEL,
        REMOVED_BACKENDS,
        REMOVED_SETUP,
        decision_endpoint,
    )

    pref = (cfg.judge_pref or "auto").strip().lower() or "auto"
    if pref == "skip" or not is_live_harness(harness_name):
        return SkipJudge()
    backend = (cfg.judge_backend or "").strip().lower()
    if backend in CHAT_BACKENDS:
        raise SkillGateError(CHAT_NOT_A_JUDGE, exit_code=2)
    ensure_builtin_decision_endpoints()
    selected = (getattr(cfg, "judge_provider", None) or "auto").strip().lower() or "auto"
    endpoint_id = "openai" if pref == "openai" else selected
    if endpoint_id in CHAT_BACKENDS:
        raise SkillGateError(CHAT_NOT_A_JUDGE, exit_code=2)
    if endpoint_id in REMOVED_BACKENDS:
        raise SkillGateError(REMOVED_SETUP, exit_code=2)
    endpoint = decision_endpoint(endpoint_id)
    if endpoint is None:
        if endpoint_id == "auto":
            return SkipJudge()
        raise SkillGateError(NOT_A_DECISION_MODEL, exit_code=2)
    return endpoint.build(cfg)


def _openai_from_cfg(cfg: LLMConfig) -> Judge:
    selected = (getattr(cfg, "judge_provider", None) or "").strip().lower()
    chosen = bool(getattr(cfg, "judge_chosen", False)) and selected == "openai"
    return _openai_judge(cfg, chosen=chosen)


def _jev_from_cfg(cfg: LLMConfig) -> Judge:
    return _jev_judge(cfg, chosen=True)


def _clef_from_cfg(cfg: LLMConfig) -> Judge:
    return _clef_judge(cfg, chosen=True)


def _openai_judge(cfg: LLMConfig, *, chosen: bool) -> Judge:
    from skillgate_ai.judge_openai import DEFAULT_BASE_URL, make_openai_judge

    api_key = (cfg.openai_api_key or "").strip()
    if not api_key:
        raise missing_openai_judge_key()
    return make_openai_judge(
        api_key=api_key,
        backend="decisions",
        model=cfg.judge_model,
        min_confidence=cfg.judge_min_confidence,
        why_enabled=False,
        reasoning_effort=cfg.judge_reasoning_effort,
        timeout_sec=cfg.judge_timeout_sec,
        base_url=DEFAULT_BASE_URL,
        display_name=_display_name("openai", chosen=chosen),
        chosen=chosen,
    )


def _jev_judge(cfg: LLMConfig, *, chosen: bool) -> Judge:
    from skillgate_ai.judge_openai import OutcomeJudge
    from skillgate_ai.judge_providers.jev import JevBackend

    key = (getattr(cfg, "jev_api_key", None) or "").strip()
    base_url = (getattr(cfg, "judge_endpoint", None) or "").strip()
    if not key:
        raise missing_provider_key("jev")
    if not base_url:
        from skillgate_ai.judge_providers.decision import NEEDS_BASE_URL

        raise SkillGateError(NEEDS_BASE_URL, exit_code=2)
    model = (getattr(cfg, "judge_provider_model", None) or "").strip() or "jev"
    backend = JevBackend(api_key=key, base_url=base_url, model=model)
    return OutcomeJudge(
        backend,
        min_confidence=cfg.judge_min_confidence,
        why_enabled=False,
        timeout_sec=cfg.judge_timeout_sec,
        display_name=_display_name("jev", chosen=chosen),
        provider="jev",
        chosen=chosen,
        supports_why=False,
        supports_confidence=False,
    )


def _clef_judge(cfg: LLMConfig, *, chosen: bool) -> Judge:
    from skillgate_ai.judge_openai import OutcomeJudge
    from skillgate_ai.judge_providers.clef import ClefBackend

    key = (getattr(cfg, "clef_api_key", None) or "").strip()
    account = (getattr(cfg, "judge_account_id", None) or "").strip()
    if not key:
        raise missing_decision_key()
    if not account:
        from skillgate_ai.judge_providers.decision import NEEDS_ACCOUNT

        raise SkillGateError(NEEDS_ACCOUNT, exit_code=2)
    model = (getattr(cfg, "judge_provider_model", None) or "").strip() or "clef"
    backend = ClefBackend(api_key=key, account_id=account, model=model)
    return OutcomeJudge(
        backend,
        min_confidence=cfg.judge_min_confidence,
        why_enabled=False,
        timeout_sec=cfg.judge_timeout_sec,
        display_name=_display_name("clef", chosen=chosen),
        provider="clef",
        chosen=chosen,
        supports_why=False,
        supports_confidence=False,
    )


def ping_judge(cfg: LLMConfig) -> dict[str, str | bool]:
    judge = resolve_judge(cfg, harness_name="cursor-agent")
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
    return {"ok": False, "message": "This decision model cannot be tested."}


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
