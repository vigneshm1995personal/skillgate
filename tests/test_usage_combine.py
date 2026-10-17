from __future__ import annotations

from skillgate_ai.usage import combine_task_usage


def test_combine_task_usage_uses_normalized_judge_usage() -> None:
    from skillgate_ai.usage import normalize_judge_api_usage

    judge_usage = normalize_judge_api_usage(
        {"usage": {"input_tokens": 500}, "completion_tokens": 25, "cost_usd": 0.01}
    )
    merged = combine_task_usage({"tokens_total": 1000, "cost_usd": 0.12}, {"usage": judge_usage})
    assert merged is not None
    assert merged["judge_cost_usd"] == 0.01
    assert merged["tokens_out"] == 25


def test_combine_task_usage_adds_agent_and_judge_cost() -> None:
    merged = combine_task_usage(
        {"tokens_total": 1000, "cost_usd": 0.12},
        {"usage": {"input_tokens": 200, "output_tokens": 50, "cost_usd": 0.03}},
    )
    assert merged is not None
    assert merged["cost_usd"] == 0.15
    assert merged["agent_cost_usd"] == 0.12
    assert merged["judge_cost_usd"] == 0.03
    assert merged["tokens_total"] == 1250
