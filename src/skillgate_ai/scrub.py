"""Scrub judge/config payloads before browser or history persistence."""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from skillgate_ai.eval_config import customer_config_label
from skillgate_ai.judge_copy import customer_scorer_name

_BROWSER_DROP = frozenset({"config_label_raw", "check_kind", "provider", "backend", "via_gateway"})

LIVE_AGENT_HARNESSES = frozenset({"cursor-agent", "codex", "claude", "claude-code"})


def _scrub_judge(judge: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in judge.items():
        if key in _BROWSER_DROP or key == "model":
            continue
        out[key] = _scrub_browser(value)
    out["display_name"] = customer_scorer_name(judge)
    return out


def _scrub_config(item: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    keep_model = (str(item.get("harness") or "").strip().lower()) in LIVE_AGENT_HARNESSES
    for key, value in item.items():
        if key in _BROWSER_DROP:
            continue
        if key == "model":
            if keep_model:
                out[key] = _scrub_browser(value)
            continue
        if key == "judge" and isinstance(value, dict):
            out[key] = _scrub_judge(value)
            continue
        if key == "applied" and isinstance(value, dict):
            applied = {k: v for k, v in value.items() if k != "via_gateway"}
            if applied:
                out[key] = applied
            continue
        out[key] = _scrub_browser(value)
    out["label"] = customer_config_label(item)
    return out


def scrub_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Scrub a run config for on-disk history. Keeps the live agent model name."""
    if config is None:
        return None
    return _scrub_config(copy.deepcopy(config))


def _scrub_browser(value: Any) -> Any:
    if isinstance(value, list):
        return [_scrub_browser(item) for item in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, item in value.items():
        if key in _BROWSER_DROP:
            continue
        if key == "judge" and isinstance(item, dict):
            out[key] = _scrub_judge(item)
            continue
        if key == "config" and isinstance(item, dict):
            out[key] = _scrub_config(item)
            continue
        if key == "model" and isinstance(item, str):
            harness = str(value.get("harness") or "").strip().lower()
            if "arm_id" in value or harness in LIVE_AGENT_HARNESSES:
                out[key] = item
            continue
        out[key] = _scrub_browser(item)
    if "scored_by" in out and isinstance(out["scored_by"], str):
        stamp = out.get("judge") if isinstance(out.get("judge"), dict) else None
        if stamp is None and isinstance(out.get("config"), dict):
            inner = out["config"].get("judge")
            stamp = inner if isinstance(inner, dict) else None
        out["scored_by"] = _neutral_scored_by(out["scored_by"], stamp)
    return out


def _neutral_scored_by(text: str, stamp: Mapping[str, Any] | None) -> str:
    from skillgate_ai.judge_copy import SCORED_BY_JUDGE, scored_by_phrase

    lower = text.lower()
    leaky = (
        "openai decisions" in lower or "vercel ai gateway" in lower or "openai couldn't" in lower
    )
    if "couldn't" in lower or "could not" in lower:
        if not leaky:
            return text
        reason = text.split(". ", 1)[1].strip() if ". " in text else ""
        if reason and ("openai" in reason.lower() or "gateway" in reason.lower()):
            reason = ""
        base = "The judge couldn't score this run."
        return f"{base} {reason}".strip() if reason else base
    if "checks scored this run" in lower:
        return text
    if isinstance(stamp, dict) and stamp.get("display_name") and ("scored by" in lower or leaky):
        return scored_by_phrase(str(stamp.get("display_name")))
    if leaky:
        return SCORED_BY_JUDGE
    return text


def scrub_browser_payload(value: Any) -> Any:
    """Copy for the local UI. Provider/model names stay on disk unless the user picked."""
    return _scrub_browser(copy.deepcopy(value))
