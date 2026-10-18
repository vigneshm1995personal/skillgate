"""Run-scoped eval config: stamp, fingerprint, and apply without mutating process env."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from skillgate_ai.config import (
    CODEX_REASONING_EFFORTS,
    DEFAULT_CODEX_REASONING_EFFORT,
    DEFAULT_OPENAI_BASE_URL,
    LLMConfig,
    normalize_codex_reasoning_effort,
)
from skillgate_ai.harness import CODEX_CHATGPT_DEFAULT
from skillgate_ai.errors import SkillGateError

SCHEMA = 1
CODEX_DEFAULT_MODEL_LABEL = "codex-default"
TIMEOUT_MIN = 1
TIMEOUT_MAX = 3600
TEMP_MIN = 0.0
TEMP_MAX = 2.0
MODEL_MAX_LEN = 120
DIFF_FIELDS = (
    "harness",
    "model",
    "timeout_sec",
    "temperature",
    "reasoning_effort",
    "judge_backend",
    "judge_model",
)


class EvalConfigError(SkillGateError):
    """Invalid run config from the UI or CLI."""

    exit_code = 2


@dataclass(frozen=True)
class EvalRunConfig:
    schema: int = SCHEMA
    harness: str = ""
    harness_pref: str = "auto"
    model: str | None = None
    requested_model: str | None = None
    timeout_sec: int | None = None
    timeout_effective: int | None = None
    temperature: float = 0.0
    reasoning_effort: str | None = None
    source: str = "env"
    applied: dict[str, bool] = field(default_factory=dict)
    judge: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "harness": self.harness,
            "harness_pref": self.harness_pref,
            "model": self.model,
            "requested_model": self.requested_model,
            "timeout_sec": self.timeout_sec,
            "timeout_effective": self.timeout_effective,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
            "source": self.source,
            "applied": dict(self.applied),
            "judge": dict(self.judge) if self.judge else None,
            "fingerprint": config_fingerprint(self),
            "label": customer_run_details(self),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> EvalRunConfig | None:
        if not data:
            return None
        applied = data.get("applied") or {}
        if not isinstance(applied, dict):
            applied = {}
        return cls(
            schema=int(data.get("schema") or SCHEMA),
            harness=str(data.get("harness") or ""),
            harness_pref=str(data.get("harness_pref") or "auto"),
            model=_blank_to_none(data.get("model")),
            requested_model=_blank_to_none(data.get("requested_model")),
            timeout_sec=_as_optional_int(data.get("timeout_sec")),
            timeout_effective=_as_optional_int(data.get("timeout_effective")),
            temperature=float(data.get("temperature") or 0.0),
            reasoning_effort=_blank_to_none(data.get("reasoning_effort")),
            source=str(data.get("source") or "env"),
            applied={str(key): bool(value) for key, value in applied.items()},
            judge=_judge_stamp(data.get("judge")),
        )


def parse_timeout_sec(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise EvalConfigError("Timeout must be a whole number of seconds (1–3600).") from exc
    if number < TIMEOUT_MIN or number > TIMEOUT_MAX:
        raise EvalConfigError("Timeout must be between 1 and 3600 seconds.")
    return number


def parse_temperature(value: Any, *, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise EvalConfigError("Temperature must be a number between 0 and 2.") from exc
    if number < TEMP_MIN or number > TEMP_MAX:
        raise EvalConfigError("Temperature must be between 0 and 2.")
    return number


def parse_model(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "\n" in text or "\r" in text:
        raise EvalConfigError("Model id cannot contain newlines.")
    if len(text) > MODEL_MAX_LEN:
        raise EvalConfigError("Model id is too long (max 120 characters).")
    return text


def parse_reasoning_effort(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    raw = str(value).strip().lower()
    if raw in CODEX_REASONING_EFFORTS:
        return raw
    raise EvalConfigError("Reasoning effort must be low, medium, high, or ultra.")


def applied_knobs(harness: str, *, model: str | None) -> dict[str, bool]:
    name = (harness or "").lower()
    if name == "codex":
        return {
            "harness": True,
            "model": bool(model),
            "timeout": True,
            "temperature": False,
            "reasoning": True,
        }
    if name in {"cursor-agent", "claude", "claude-code"}:
        return {
            "harness": True,
            "model": bool(model),
            "timeout": True,
            "temperature": False,
            "reasoning": False,
        }
    return {
        "harness": True,
        "model": False,
        "timeout": True,
        "temperature": False,
        "reasoning": False,
    }


def resolve_eval_config(
    *,
    harness_pref: str,
    incoming: dict[str, Any] | None,
    cfg: LLMConfig,
    source: str,
    resolved_harness: str = "",
) -> EvalRunConfig:
    payload = incoming or {}
    model = parse_model(payload.get("model"))
    timeout_sec = parse_timeout_sec(payload.get("timeout_sec"))
    temperature = parse_temperature(payload.get("temperature"), default=cfg.temperature)
    effort = parse_reasoning_effort(payload.get("reasoning_effort"))
    run = EvalRunConfig(
        harness=resolved_harness,
        harness_pref=(harness_pref or "auto").strip().lower() or "auto",
        model=model,
        requested_model=model,
        timeout_sec=timeout_sec,
        temperature=temperature,
        reasoning_effort=effort,
        source=source,
        applied=applied_knobs(resolved_harness, model=model),
    )
    if resolved_harness:
        return stamp_resolved(run, resolved_harness, cfg)
    return run


def apply_eval_config(cfg: LLMConfig, run: EvalRunConfig) -> LLMConfig:
    """Return a replaced LLMConfig. Never assign os.environ."""
    updates: dict[str, Any] = {"temperature": run.temperature}
    if run.model:
        updates["gateway_model"] = run.model
        updates["anthropic_model"] = run.model
        updates["codex_model"] = run.model
        updates["cursor_model"] = run.model
    if run.reasoning_effort:
        updates["codex_reasoning_effort"] = normalize_codex_reasoning_effort(run.reasoning_effort)
    return replace(cfg, **updates)


def stamp_resolved(run: EvalRunConfig, harness_name: str, cfg: LLMConfig) -> EvalRunConfig:
    name = (harness_name or "").strip().lower()
    model = run.model
    effort = run.reasoning_effort
    if name == "codex":
        if model is None:
            model = (cfg.codex_model or "").strip() or None
        if not model or model == CODEX_DEFAULT_MODEL_LABEL:
            model = CODEX_CHATGPT_DEFAULT
        if effort is None:
            effort = cfg.codex_reasoning_effort or DEFAULT_CODEX_REASONING_EFFORT
    elif name == "cursor-agent":
        if model is None:
            model = cfg.cursor_model
        effort = None
    elif name in {"claude", "claude-code"}:
        if model is None:
            model = (cfg.anthropic_model or "").strip() or None
        effort = None
    else:
        effort = None
    applied = applied_knobs(name, model=run.model)
    return replace(
        run,
        harness=name,
        model=model,
        reasoning_effort=effort,
        applied=applied,
    )


def with_timeout_effective(run: EvalRunConfig, effective: int | None) -> EvalRunConfig:
    return replace(run, timeout_effective=effective)


def with_model(run: EvalRunConfig, model: str | None) -> EvalRunConfig:
    """Record the model the harness actually used (keeps applied.model untouched)."""
    resolved = (model or "").strip() or None
    previous = (run.model or "").strip() or None
    requested = run.requested_model or (previous if previous and previous != resolved else None)
    return replace(run, model=resolved, requested_model=requested)


def with_judge(run: EvalRunConfig, stamp: dict[str, str] | None) -> EvalRunConfig:
    return replace(run, judge=dict(stamp) if stamp else None)


def config_fingerprint(run: EvalRunConfig | None) -> str | None:
    if run is None:
        return None
    effort = ""
    if run.harness == "codex":
        effort = run.reasoning_effort or DEFAULT_CODEX_REASONING_EFFORT
    timeout = run.timeout_effective
    if timeout is None:
        timeout = run.timeout_sec or 0
    payload = {
        "harness": run.harness or "",
        "model": run.model or "",
        "timeout_sec": timeout,
        "temperature": run.temperature,
        "reasoning_effort": effort,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def harness_display_name(pref: str | None, resolved: str | None = None) -> str:
    from skillgate_ai.config import agent_label

    key = (pref or resolved or "").strip().lower()
    if key == "auto":
        resolved_key = (resolved or "").strip().lower()
        if resolved_key in {"codex", "claude", "cursor-agent", "claude-code"}:
            return f"Auto · {agent_label(resolved_key)}"
        return "Auto"
    if key in {"cursor-agent", "cursor", "codex", "claude", "claude-code"}:
        return agent_label(key)
    return (pref or resolved or "Auto").strip() or "Auto"


OLDER_RUN_LABEL = "Older run (before live-only checks)"


def is_legacy_run_config(
    run: EvalRunConfig | dict[str, Any] | None, harness: str | None = None
) -> bool:
    cfg = coerce_eval_config(run)
    key = (harness or (cfg.harness if cfg else "") or "").strip().lower()
    if key in {"skip", "demo"}:
        return True
    stored = ""
    if isinstance(run, dict):
        stored = str(run.get("label") or "")
    return "checker" in stored.lower()


def friendly_model_name(model: str | None) -> str:
    raw = (model or "").strip()
    if not raw:
        return ""
    slug = raw.rsplit("/", 1)[-1]
    if re.match(r"^(claude|cursor|codex|openai|anthropic|gemini)([-_]|$)", slug, flags=re.IGNORECASE):
        return slug
    match = re.match(r"^gpt-(.+)$", slug, flags=re.IGNORECASE)
    if match:
        ver, *tail = match.group(1).split("-")
        extras: list[str] = []
        for part in tail:
            lower = part.lower()
            extras.append(lower if lower in {"mini", "nano", "preview"} else part)
        return " ".join([f"GPT-{ver}", *extras]).strip()
    parts = re.split(r"[-_]", slug)
    titled: list[str] = []
    for part in parts:
        if not part:
            continue
        if re.fullmatch(r"\d+(\.\d+)*", part):
            titled.append(part)
        else:
            titled.append(part[:1].upper() + part[1:])
    return " ".join(titled)


_OPENAI_SCORER = re.compile(r"\bopenai\b(?!/)", re.IGNORECASE)
_VENDOR_SCORER = re.compile(r"\b(?:openai(?!/)|jev|clef|aws|cloudflare)\b", re.IGNORECASE)


def is_openai_scorer_text(*parts: str) -> bool:
    blob = " ".join(parts)
    return bool(_OPENAI_SCORER.search(blob)) or "scored by the judge" in blob.lower()


def _is_openai_scorer(cfg: EvalRunConfig, extra: str = "") -> bool:
    judge = cfg.judge or {}
    display = str(judge.get("display_name") or "")
    provider = str(judge.get("provider") or "")
    if provider.lower() == "openai":
        return True
    return is_openai_scorer_text(display, extra)


def customer_config_label(
    run: EvalRunConfig | dict[str, Any] | None, harness: str | None = None
) -> str:
    if is_legacy_run_config(run, harness):
        return OLDER_RUN_LABEL
    raw_label = str(run.get("label") or "") if isinstance(run, dict) else ""
    cfg = coerce_eval_config(run)
    if cfg is None and harness:
        return harness_display_name(harness)
    if cfg is None:
        return ""
    judge = cfg.judge or {}
    from skillgate_ai.judge_copy import CHOSEN_LABELS, customer_scorer_name, scored_by_phrase

    provider = str(judge.get("provider") or "").lower()
    if provider and provider != "skip":
        return scored_by_phrase(customer_scorer_name(judge))
    name = customer_scorer_name(judge)
    if name in CHOSEN_LABELS.values():
        return scored_by_phrase(name)
    if _is_openai_scorer(cfg, raw_label) or _VENDOR_SCORER.search(raw_label):
        return "Scored by the judge"
    if _VENDOR_SCORER.search(str(judge.get("display_name") or "")):
        return "Scored by the judge"
    if raw_label.startswith("Scored by "):
        return raw_label
    if harness:
        return harness_display_name(harness)
    return ""


def customer_run_details(
    run: EvalRunConfig | dict[str, Any] | None, harness: str | None = None
) -> str:
    if is_legacy_run_config(run, harness):
        return OLDER_RUN_LABEL
    cfg = coerce_eval_config(run)
    if cfg is None:
        return harness_display_name(harness) if harness else ""
    parts: list[str] = []
    name = harness_display_name(cfg.harness or harness, cfg.harness)
    if name:
        parts.append(name)
    show_model = bool((cfg.applied or {}).get("model")) or (
        (cfg.harness or "").strip().lower() in {"codex", "claude", "claude-code"}
        and bool(cfg.model)
    )
    if show_model:
        model = friendly_model_name(cfg.model)
        if model:
            parts.append(model)
    timeout = cfg.timeout_effective if cfg.timeout_effective is not None else cfg.timeout_sec
    if timeout:
        parts.append(f"{timeout}s")
    return " · ".join(parts)


def config_label(run: EvalRunConfig | dict[str, Any] | None) -> str:
    cfg = coerce_eval_config(run)
    if cfg is None:
        return ""
    parts: list[str] = [harness_display_name(cfg.harness, cfg.harness)]
    if cfg.model:
        model = friendly_model_name(cfg.model)
        if model:
            parts.append(model)
    timeout = cfg.timeout_effective if cfg.timeout_effective is not None else cfg.timeout_sec
    if timeout:
        parts.append(f"{timeout}s")
    if cfg.harness == "codex":
        parts.append(cfg.reasoning_effort or DEFAULT_CODEX_REASONING_EFFORT)
    elif cfg.temperature not in (0, 0.0) and (cfg.applied or {}).get("temperature"):
        parts.append(f"temp {cfg.temperature}")
    return " · ".join(parts)


def diff_eval_config(
    current: EvalRunConfig | dict[str, Any] | None,
    previous: EvalRunConfig | dict[str, Any] | None,
) -> list[dict[str, Any]]:
    now = coerce_eval_config(current)
    then = coerce_eval_config(previous)
    if now is None or then is None:
        return []
    if not config_fingerprint(now) or not config_fingerprint(then):
        return []
    current_view = _diff_view(now)
    previous_view = _diff_view(then)
    entries: list[dict[str, Any]] = []
    for name in DIFF_FIELDS:
        if current_view[name] != previous_view[name]:
            entries.append({"field": name, "from": previous_view[name], "to": current_view[name]})
    return entries


def coerce_eval_config(value: EvalRunConfig | dict[str, Any] | None) -> EvalRunConfig | None:
    if value is None:
        return None
    if isinstance(value, EvalRunConfig):
        return value
    if isinstance(value, dict):
        return EvalRunConfig.from_dict(value)
    return None


def _diff_view(run: EvalRunConfig) -> dict[str, Any]:
    timeout = run.timeout_effective if run.timeout_effective is not None else run.timeout_sec
    effort = None
    if run.harness == "codex":
        effort = run.reasoning_effort or DEFAULT_CODEX_REASONING_EFFORT
    judge = run.judge or {}
    return {
        "harness": run.harness or None,
        "model": run.model,
        "timeout_sec": timeout,
        "temperature": run.temperature,
        "reasoning_effort": effort,
        "judge_backend": str(judge.get("backend") or "") or None,
        "judge_model": str(judge.get("model") or "") or None,
    }


def _judge_stamp(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    stamp = {
        str(key): str(item)
        for key, item in value.items()
        if item is not None and str(key).lower() not in {"api_key", "key", "authorization"}
    }
    return stamp or None


def _blank_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
