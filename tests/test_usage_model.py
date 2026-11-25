from __future__ import annotations

import pytest

from skillgate_ai.usage import (
    Usage,
    estimate_usage_cost_usd,
    merge_usage,
    parse_usage_line,
    usage_from_mapping,
)


def test_merge_usage_is_monotonic() -> None:
    assert merge_usage(
        Usage(tokens_in=10, tokens_total=20),
        Usage(tokens_in=5, tokens_out=3),
    ) == Usage(tokens_in=10, tokens_out=3, tokens_total=20, cost_usd=None)


def test_estimate_usage_cost_prefers_reported_cost() -> None:
    assert estimate_usage_cost_usd("x", Usage(cost_usd=0.5)) == 0.5
    assert estimate_usage_cost_usd("x", None) is None


def test_estimate_usage_cost_uses_longest_prefix_match() -> None:
    cost = estimate_usage_cost_usd(
        "anthropic/claude-sonnet-4-5-latest",
        Usage(tokens_in=1_000_000, tokens_out=0),
    )
    assert cost == 3.0


def test_estimate_usage_cost_total_only_counts_as_input() -> None:
    assert estimate_usage_cost_usd("gpt-5.6-luna", Usage(tokens_total=2_000_000)) == 0.2


def test_usage_from_mapping_rejects_non_dict() -> None:
    assert usage_from_mapping([1]) is None


@pytest.mark.parametrize("line", ["hello", "{bad", "[1]"])
def test_parse_usage_line_ignores_non_json(line: str) -> None:
    assert parse_usage_line(line) is None
