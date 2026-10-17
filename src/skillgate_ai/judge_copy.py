"""Customer-facing scoring copy. Names a vendor only when the user picked one."""

from __future__ import annotations

from typing import Any, Mapping

YOUR_JUDGE = "your judge"
CHOSEN_LABELS = {
    "openai": "OpenAI",
    "jev": "Jev",
    "aws": "AWS",
    "compatible": YOUR_JUDGE,
}
DEFAULT_NAME = "the judge"
SKIP_NAME = "Checks"
SCORED_BY_JUDGE = "Scored by the judge"
SCORED_BY_YOUR_JUDGE = "Scored by your judge"
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
    display = str(stamp.get("display_name") or "").strip()
    if provider in {"compatible", "other"} or display.lower() in {"other", YOUR_JUDGE}:
        return YOUR_JUDGE
    if provider in {"jev", "aws"}:
        return CHOSEN_LABELS[provider]
    if provider == "skip":
        return SKIP_NAME
    if display in CHOSEN_LABELS.values():
        return display
    if display == SKIP_NAME:
        return SKIP_NAME
    if stamp_is_chosen(stamp):
        return CHOSEN_LABELS.get(provider, DEFAULT_NAME)
    return DEFAULT_NAME


def scored_by_phrase(name: str) -> str:
    if (name or "").strip().lower() in {"other", YOUR_JUDGE}:
        return SCORED_BY_YOUR_JUDGE
    if name == SKIP_NAME:
        return SCORED_BY_CHECKS
    if name == DEFAULT_NAME or not name:
        return SCORED_BY_JUDGE
    return f"Scored by {name}"


def title_scorer(name: str) -> str:
    if (name or "").strip().lower() in {YOUR_JUDGE, "other"}:
        return "Your judge"
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
