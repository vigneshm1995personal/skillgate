from __future__ import annotations

from dataclasses import dataclass

# Order matters: prefer the harness's own underscore names, then OpenAI's
# prompt/completion names, then Cursor's camelCase, then short aliases.
_IN_KEYS = ("tokens_in", "input_tokens", "prompt_tokens", "inputTokens", "input")
_OUT_KEYS = ("tokens_out", "output_tokens", "completion_tokens", "outputTokens", "output")
_TOTAL_KEYS = ("tokens_total", "total_tokens", "totalTokens")
# USD per 1M tokens (input, output) for models Skill Gate commonly runs.
_MODEL_USD_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-5.6-luna": (0.10, 0.50),
    "gpt-5.6-terra": (1.25, 10.00),
    "gpt-5.6-sol": (0.25, 2.00),
    "gpt-6-astra": (0.10, 0.50),
    "composer-2.5": (1.25, 10.00),
    "composer-2.5-fast": (0.50, 4.00),
    "codex-default": (1.25, 10.00),
    "claude-fable-5-1": (10.00, 50.00),
    "claude-fable-5": (10.00, 50.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-sonnet-4-20250514": (3.00, 15.00),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.00, 5.00),
}

SUBSCRIPTION_COST_LABEL = "subscription (not metered)"

_COST_KEYS = (
    "cost_usd",
    "total_cost_usd",
    "total_usd",
    "costUsd",
    "totalCostUsd",
    "cost",
    "total_cost",
)

_CODEX_BOOKKEEPING = frozenset({"thread.started", "turn.started", "turn.completed"})
# Cursor stream-json envelopes that carry no human text for the live tail.
_CURSOR_BOOKKEEPING = frozenset({"system", "user", "result"})
# Claude / Cursor events that are account or transport noise, not evidence.
_NON_CONTENT_EVENTS = frozenset(
    {
        "rate_limit_event",
        "system",
        "ping",
        "stream_event",
        "hook_started",
        "hook_progress",
        "hook_response",
        "prompt_suggestion",
    }
)


@dataclass(frozen=True)
class Usage:
    tokens_in: int | None = None
    tokens_out: int | None = None
    tokens_total: int | None = None
    cost_usd: float | None = None

    @property
    def known(self) -> bool:
        return any(
            value is not None
            for value in (
                self.tokens_in,
                self.tokens_out,
                self.tokens_total,
                self.cost_usd,
            )
        )

    def to_dict(self) -> dict[str, float | int | None]:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_total": self.tokens_total,
            "cost_usd": self.cost_usd,
        }
