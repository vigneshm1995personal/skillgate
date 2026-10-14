from __future__ import annotations

from skillgate_ai.usage import combine_task_usage


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
