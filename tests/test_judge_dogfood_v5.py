"""Regression tests from dogfood v5 judge calibration."""

from __future__ import annotations

import json

from skillgate_ai.gate import _quality_scoring_was_skipped
from skillgate_ai.judge_bank import outcome_verdict
from skillgate_ai.judge_context import (
    build_agent_trajectory,
    parse_command_runs,
    workspace_files_for_judge,
)
from skillgate_ai.judge_openai import _state_text
from skillgate_ai.usage import normalize_judge_api_usage


def test_instruction_minor_deviation_passes_lock() -> None:
    passed, reasons = outcome_verdict(
        {
            "task_completion": {"choice": "Fully completed"},
            "correctness": {"choice": "Correct"},
            "instruction_adherence": {"choice": "Minor deviation"},
            "evidence_action_validity": {"choice": "Fully supported"},
            "result_quality": {"choice": "Clear and complete"},
        }
    )
    assert passed is True
    assert reasons == []


def test_state_payload_includes_workspace_files_and_command_runs() -> None:
    transcript = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "pytest -q output/test_slugify.py",
                "aggregated_output": "1 passed in 0.12s",
                "exit_code": 0,
            },
        }
    )
    trajectory = build_agent_trajectory(
        spans=[],
        transcript=transcript,
        path={"steps": 2, "errors": 0, "had_path": True},
        scores=[],
        artifacts=[
            {
                "path": "output/slugify.py",
                "present": True,
                "body": "def slugify(text: str) -> str:\n    return text.lower()",
            },
            {
                "path": "output/test_slugify.py",
                "present": True,
                "body": "def test_slugify():\n    assert slugify('Hi') == 'hi'",
            },
        ],
    )
    assert trajectory["command_runs"][0]["command"].startswith("pytest")
    assert "passed" in (trajectory["command_runs"][0].get("output") or "").lower()
    payload = json.loads(
        _state_text(
            {
                "check_prompt": "Implement slugify with tests",
                "skill_instructions": "Always write tests first.",
                "artifacts": [
                    {"path": "output/slugify.py", "present": True, "body": "def slugify"},
                ],
                "agent_trajectory": trajectory,
            }
        )
    )
    assert payload["workspace_files"][0]["content"] == "def slugify"
    assert payload["agent_trajectory"]["command_runs"][0]["output"]


def test_parse_command_runs_from_jsonl() -> None:
    line = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "python -m pytest -q",
                "stdout": "2 passed",
            },
        }
    )
    runs = parse_command_runs(line)
    assert runs[0]["command"] == "python -m pytest -q"
    assert runs[0]["output"] == "2 passed"


def test_normalize_judge_api_usage_merges_top_level_tokens_and_cost() -> None:
    usage = normalize_judge_api_usage(
        {
            "usage": {"input_tokens": 1200},
            "output_tokens": 88,
            "total_cost_usd": 0.014,
        }
    )
    assert usage is not None
    assert usage["tokens_in"] == 1200
    assert usage["tokens_out"] == 88
    assert usage["cost_usd"] == 0.014


def test_quality_scoring_skipped_when_judge_http_error() -> None:
    from skillgate_ai.engine import SuiteReport, TaskReport

    report = SuiteReport(
        suite="x",
        title="t",
        skill="pdf",
        harness="claude",
        sandbox="local",
        passed=False,
        tasks=[
            TaskReport(
                task_id="t1",
                prompt="p",
                expect_skill="pdf",
                passed=False,
                scores=[],
                selected_skill="pdf",
                judge={"status": "error", "reasons": ["HTTP 402"]},
            )
        ],
    )
    assert _quality_scoring_was_skipped(report) is True


def test_workspace_files_for_judge_caps_content() -> None:
    rows = workspace_files_for_judge(
        [{"path": "output/a.txt", "present": True, "body": "x" * 10_000}]
    )
    assert len(rows[0]["content"]) <= 6000
