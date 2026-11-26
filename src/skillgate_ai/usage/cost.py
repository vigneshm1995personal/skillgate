from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from skillgate_ai.usage.model import (
    _COST_KEYS,
    _IN_KEYS,
    _MODEL_USD_PER_MILLION,
    _OUT_KEYS,
    _TOTAL_KEYS,
    SUBSCRIPTION_COST_LABEL,
    Usage,
)
from skillgate_ai.usage.parse import merge_usage, usage_from_mapping


def _add_int(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return int(left or 0) + int(right or 0)


def _add_float(left: float | None, right: float | None) -> float | None:
    if left is None and right is None:
        return None
    return round(float(left or 0.0) + float(right or 0.0), 6)


def _normalize_model_id(model: str | None) -> str:
    raw = (model or "").strip().lower()
    if not raw:
        return ""
    if "/" in raw:
        raw = raw.split("/")[-1]
    return raw


def estimate_usage_cost_usd(model: str | None, usage: Usage | None) -> float | None:
    """Estimate dollars from token counts when the API omitted cost."""
    if usage is None or usage.cost_usd is not None:
        return usage.cost_usd if usage else None
    key = _normalize_model_id(model)
    if not key:
        return None
    prices = _MODEL_USD_PER_MILLION.get(key)
    if prices is None:
        best: tuple[str, tuple[float, float]] | None = None
        for name, rate in _MODEL_USD_PER_MILLION.items():
            if (key.startswith(name) or name.startswith(key)) and (
                best is None or len(name) > len(best[0])
            ):
                best = (name, rate)
        if best is not None:
            prices = best[1]
    if prices is None:
        return None
    tin = int(usage.tokens_in or 0)
    tout = int(usage.tokens_out or 0)
    if tin == 0 and tout == 0 and usage.tokens_total is None:
        return None
    if tin == 0 and tout == 0 and usage.tokens_total is not None:
        tin = int(usage.tokens_total)
    cost = (tin * prices[0] + tout * prices[1]) / 1_000_000.0
    return round(cost, 6)


def normalize_judge_api_usage(
    data: Any,
    *,
    model: str | None = None,
) -> dict[str, float | int | None] | None:
    """Flatten Decisions / chat usage + optional cost fields from an API response."""
    if not isinstance(data, dict):
        return None
    merged = Usage()
    parts: list[dict[str, Any]] = []
    usage = data.get("usage")
    if isinstance(usage, dict):
        parts.append(usage)
    top_level = {
        key: data[key] for key in (*_IN_KEYS, *_OUT_KEYS, *_TOTAL_KEYS, *_COST_KEYS) if key in data
    }
    if top_level:
        parts.append(top_level)
    parts.append(data)
    for part in parts:
        parsed = usage_from_mapping(part)
        if parsed is not None:
            merged = merge_usage(merged, parsed) if merged.known else parsed
    if not merged.known:
        return None
    resolved_model = str(data.get("model") or model or "").strip() or None
    if merged.cost_usd is None:
        estimated = estimate_usage_cost_usd(resolved_model, merged)
        if estimated is not None:
            merged = Usage(
                tokens_in=merged.tokens_in,
                tokens_out=merged.tokens_out,
                tokens_total=merged.tokens_total,
                cost_usd=estimated,
            )
    return merged.to_dict()


def combine_task_usage(
    agent: Mapping[str, Any] | None,
    judged: dict[str, Any] | None,
    *,
    agent_model: str | None = None,
    judge_model: str | None = None,
    agent_subscription: bool = False,
) -> dict[str, Any] | None:
    """Merge harness usage with the judge call's usage for check results."""
    agent_u = usage_from_mapping(agent)
    judge_raw = judged.get("usage") if isinstance(judged, dict) else None
    judge_u = usage_from_mapping(judge_raw)
    if agent_u is None and judge_u is None:
        return None if agent is None else dict(agent)
    if agent_subscription and agent_u is not None:
        agent_u = Usage(
            tokens_in=agent_u.tokens_in,
            tokens_out=agent_u.tokens_out,
            tokens_total=agent_u.tokens_total,
            cost_usd=None,
        )
    elif agent_u is not None and agent_u.cost_usd is None:
        est = estimate_usage_cost_usd(agent_model, agent_u)
        if est is not None:
            agent_u = Usage(
                tokens_in=agent_u.tokens_in,
                tokens_out=agent_u.tokens_out,
                tokens_total=agent_u.tokens_total,
                cost_usd=est,
            )
    if judge_u is not None and judge_u.cost_usd is None:
        jmodel = judge_model
        if isinstance(judged, dict) and not jmodel:
            jmodel = str(judged.get("model") or "").strip() or None
        est = estimate_usage_cost_usd(jmodel, judge_u)
        if est is not None:
            judge_u = Usage(
                tokens_in=judge_u.tokens_in,
                tokens_out=judge_u.tokens_out,
                tokens_total=judge_u.tokens_total,
                cost_usd=est,
            )
    agent_cost = agent_u.cost_usd if agent_u else None
    judge_cost = judge_u.cost_usd if judge_u else None
    total_cost = _add_float(agent_cost, judge_cost)
    out: dict[str, Any] = {
        "tokens_in": _add_int(
            agent_u.tokens_in if agent_u else None,
            judge_u.tokens_in if judge_u else None,
        ),
        "tokens_out": _add_int(
            agent_u.tokens_out if agent_u else None,
            judge_u.tokens_out if judge_u else None,
        ),
        "tokens_total": _add_int(
            agent_u.tokens_total if agent_u else None,
            judge_u.tokens_total if judge_u else None,
        ),
        "cost_usd": total_cost,
    }
    if agent_cost is not None:
        out["agent_cost_usd"] = agent_cost
    if judge_cost is not None:
        out["judge_cost_usd"] = judge_cost
    tokens_seen = (
        out.get("tokens_total") is not None
        or out.get("tokens_in") is not None
        or out.get("tokens_out") is not None
    )
    if agent_subscription:
        out["agent_cost_label"] = SUBSCRIPTION_COST_LABEL
    if tokens_seen and total_cost is None and not agent_subscription:
        out["cost_unknown"] = True
    elif total_cost is not None:
        out.pop("cost_unknown", None)
    return {key: value for key, value in out.items() if value is not None}
