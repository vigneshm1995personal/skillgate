"""Customer-facing scoring copy. Names a vendor only when the user picked one."""

from __future__ import annotations

from typing import Any, Mapping

CHOSEN_LABELS = {
    "openai": "OpenAI",
    "jev": "Jev",
    "aws": "AWS",
    "compatible": "Other",
}
DEFAULT_NAME = "the judge"
SKIP_NAME = "Checks"
SCORED_BY_JUDGE = "Scored by the judge"
SCORED_BY_CHECKS = "Scored by Checks"


def stamp_is_chosen(stamp: Mapping[str, Any] | None) -> bool:
    if not isinstance(stamp, Mapping):
        return False
    raw = stamp.get("chosen")
    if raw is True:
        return True
    if isinstance(raw, str) and raw.strip().lower() in {"1", "true", "yes"}:
        return True
    return False


def customer_scorer_name(stamp: Mapping[str, Any] | None) -> str:
    if not isinstance(stamp, Mapping):
        return DEFAULT_NAME
    provider = str(stamp.get("provider") or "").strip().lower()
    if provider in {"skip", ""}:
        if not provider:
            return DEFAULT_NAME
        return SKIP_NAME
    if provider in {"jev", "aws", "compatible"}:
        return CHOSEN_LABELS[provider]
    if stamp_is_chosen(stamp):
        return CHOSEN_LABELS.get(provider, DEFAULT_NAME)
    return DEFAULT_NAME


def scored_by_phrase(name: str) -> str:
    if name == SKIP_NAME:
        return SCORED_BY_CHECKS
    if name == DEFAULT_NAME or not name:
        return SCORED_BY_JUDGE
    return f"Scored by {name}"


def title_scorer(name: str) -> str:
    if name == DEFAULT_NAME or not name:
        return "The judge"
    return name


def couldnt_score_line(stamp: Mapping[str, Any] | None, reason: str | None = None) -> str:
    who = title_scorer(customer_scorer_name(stamp))
    base = f"{who} couldn't score this run."
    extra = (reason or "").strip()
    if extra and extra.lower() not in base.lower():
        return f"{base} {extra}"
    return base


def unusable_answer_text(stamp: Mapping[str, Any] | None = None) -> str:
    who = title_scorer(customer_scorer_name(stamp))
    return f"{who} returned an unusable answer."


def scoring_failed_text(stamp: Mapping[str, Any] | None = None) -> str:
    who = title_scorer(customer_scorer_name(stamp))
    return f"{who} couldn't score this check."
