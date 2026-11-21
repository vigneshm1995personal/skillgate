from __future__ import annotations

import json

from skillgate_ai.harness import _jsonl_transcript
from skillgate_ai.usage import combine_task_usage, parse_usage_line, render_stream_line


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


_RATE_LIMIT = json.dumps(
    {
        "type": "rate_limit_event",
        "rate_limit_info": {"status": "allowed", "utilization": 0.38},
    }
)
_SYSTEM_INIT = json.dumps(
    {
        "type": "system",
        "subtype": "init",
        "cwd": "/tmp/skillgate-ws",
        "model": "claude-sonnet-5-5",
    }
)


def _tool_pair() -> str:
    return "\n".join(
        [
            _SYSTEM_INIT,
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "toolu_bash",
                                "name": "Bash",
                                "input": {"command": "pytest -q output/test_slugify.py"},
                            }
                        ]
                    },
                }
            ),
            _RATE_LIMIT,
            json.dumps(
                {
                    "type": "user",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "toolu_bash",
                                "content": "1 passed in 0.12s",
                            }
                        ]
                    },
                }
            ),
            _RATE_LIMIT,
        ]
    )


def test_render_drops_claude_rate_limit_and_system_events() -> None:
    assert render_stream_line(_RATE_LIMIT) is None
    assert render_stream_line(_SYSTEM_INIT) is None
    rendered = _jsonl_transcript(_tool_pair(), "")
    assert "rate_limit_event" not in rendered
    assert "utilization" not in rendered
    assert "subtype" not in rendered
    assert "pytest -q output/test_slugify.py" in rendered
    assert "1 passed in 0.12s" in rendered


def test_parse_claude_result_total_cost_usd() -> None:
    line = (
        '{"type":"result","subtype":"success","total_cost_usd":0.0421,'
        '"usage":{"inputTokens":100,"outputTokens":50}}'
    )
    usage = parse_usage_line(line)
    assert usage is not None
    assert usage.cost_usd == 0.0421
    assert usage.tokens_in == 100
    assert usage.tokens_out == 50
