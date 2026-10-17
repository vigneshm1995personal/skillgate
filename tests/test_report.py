from __future__ import annotations

from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.judge_openai import OUT_OF_CREDITS
from skillgate_ai.report import format_cli, format_github, report_to_dict, scored_by_line
from skillgate_ai.scorers import Score
from skillgate_ai.usage import SUBSCRIPTION_COST_LABEL


def _task(*, judge: dict | None, passed: bool = True, task_id: str = "t1") -> TaskReport:
    return TaskReport(
        task_id=task_id,
        prompt="p",
        expect_skill="pdf",
        passed=passed,
        scores=[],
        selected_skill="pdf",
        failures=[] if passed else ["failed"],
        judge=judge,
    )


def _report(*, harness: str, tasks: list[TaskReport], config: dict | None = None) -> SuiteReport:
    return SuiteReport(
        suite="suite",
        title="title",
        skill="pdf",
        harness=harness,
        sandbox="local",
        passed=all(task.passed for task in tasks),
        tasks=tasks,
        config=config,
    )


def test_scored_by_openai_error_not_claimed_as_scored() -> None:
    report = _report(
        harness="cursor-agent",
        config={"judge": {"provider": "openai", "display_name": "OpenAI (your key)"}},
        tasks=[
            _task(
                passed=False,
                judge={
                    "status": "error",
                    "provider": "openai",
                    "display_name": "OpenAI (your key)",
                    "answers": {},
                    "reasons": [OUT_OF_CREDITS],
                },
            )
        ],
    )
    line = scored_by_line(report)
    assert line.startswith("The judge couldn't score this run.")
    assert "out of credits" in line
    assert "scored this run" not in line
    assert "OpenAI couldn't" not in line
    text = format_cli(report)
    assert "OpenAI (your key) scored this run." not in text
    assert "OpenAI couldn't score this run." not in text
    assert "The judge couldn't score this run." in text


def test_scored_by_skip_on_live_does_not_deny_live_model() -> None:
    report = _report(
        harness="cursor-agent",
        config={"judge": {"provider": "skip", "display_name": "Built-in checker"}},
        tasks=[
            _task(
                judge={
                    "status": "skip",
                    "provider": "skip",
                    "display_name": "Built-in checker",
                    "passed": None,
                }
            )
        ],
    )
    line = scored_by_line(report)
    assert line == "The skill ran live. Quality was not scored."
    assert "not a live model" not in line.lower()
    text = format_cli(report)
    assert "not a live model" not in text.lower()
    assert "ran live" in text


def test_scored_by_skip_without_live_harness() -> None:
    report = _report(
        harness="demo",
        config={"judge": {"provider": "skip", "display_name": "Built-in checker"}},
        tasks=[_task(judge=None)],
    )
    assert scored_by_line(report) == "Quality was not scored."


def test_scored_by_openai_with_answers() -> None:
    report = _report(
        harness="cursor-agent",
        config={"judge": {"provider": "openai", "display_name": "OpenAI (your key)"}},
        tasks=[
            _task(
                judge={
                    "status": "completed",
                    "provider": "openai",
                    "display_name": "OpenAI (your key)",
                    "answers": {"task_completion": {"choice": "Fully completed"}},
                }
            )
        ],
    )
    assert scored_by_line(report) == "Scored by the judge"
    text = format_cli(report)
    assert "Scored by the judge" in text
    assert "Scored by OpenAI" not in text
    assert "OpenAI (your key)" not in text
    assert "OpenAI Decisions" not in text
    assert "OpenAI (your key) scored this run." not in text
    gateway = _report(
        harness="cursor-agent",
        config={
            "judge": {
                "provider": "openai",
                "display_name": "OpenAI Decisions via Vercel AI Gateway (your key)",
            }
        },
        tasks=[
            _task(
                judge={
                    "status": "completed",
                    "provider": "openai",
                    "display_name": "OpenAI Decisions via Vercel AI Gateway (your key)",
                    "answers": {"task_completion": {"choice": "Fully completed"}},
                }
            )
        ],
    )
    assert scored_by_line(gateway) == "Scored by the judge"
    cli = format_cli(gateway)
    assert "Scored by the judge" in cli
    assert "via Vercel" not in scored_by_line(gateway)
    assert "via Vercel" not in cli
    assert "OpenAI Decisions" not in cli
    assert "gpt-6-luna" not in cli


def test_happened_never_blank_on_pass() -> None:
    payload = report_to_dict(_report(harness="demo", tasks=[_task(judge=None, passed=True)]))
    row = payload["tasks"][0]
    assert row["happened"] == "Output matched what was expected."
    assert row["check_kind"] == "builtin"


def test_happened_no_trigger_pass_is_plain() -> None:
    task = _task(judge=None, passed=True)
    task.expect_skill = None
    task.selected_skill = None
    payload = report_to_dict(_report(harness="cursor-agent", tasks=[task]))
    assert payload["tasks"][0]["happened"] == "No skill was picked, as expected."


def test_happened_uses_warning_on_pass() -> None:
    payload = report_to_dict(
        _report(
            harness="cursor-agent",
            tasks=[
                _task(
                    passed=True,
                    judge={"warnings": ["The judge wasn't very sure about this one."]},
                )
            ],
        )
    )
    assert payload["tasks"][0]["happened"] == "The judge wasn't very sure about this one."
    text = format_github(
        _report(
            harness="cursor-agent",
            tasks=[
                _task(
                    passed=True,
                    judge={"warnings": ["The judge wasn't very sure about this one."]},
                )
            ],
        )
    )
    assert "Output matched what was expected." not in text
    assert "The judge wasn't very sure about this one." in text


def test_happened_uses_why_on_fail() -> None:
    payload = report_to_dict(
        _report(
            harness="cursor-agent",
            tasks=[_task(passed=False, judge={"why": "Wrong file."})],
        )
    )
    assert payload["tasks"][0]["happened"] == "Wrong file."


def test_check_answers_from_openai_cells() -> None:
    payload = report_to_dict(
        _report(
            harness="cursor-agent",
            tasks=[
                _task(
                    judge={
                        "status": "completed",
                        "cells": {
                            "task_completion": {
                                "label": "Got the job done?",
                                "choice": "Fully completed",
                            },
                            "path_efficiency": {
                                "label": "How it ran",
                                "choice": None,
                                "reason": "Not available. No recorded path.",
                            },
                        },
                    }
                )
            ],
        )
    )
    row = payload["tasks"][0]
    assert row["check_kind"] == "openai"
    answers = {item["label"]: item["answer"] for item in row["check_answers"]}
    assert answers["Got the job done?"] == "Fully completed"
    assert answers["How it ran"] == "Not available"


def test_check_answers_from_builtin_scores() -> None:
    task = _task(judge={"status": "skip", "cells": []})
    task.scores = [
        Score(
            scorer="task_completion",
            passed=True,
            detail="All expected outputs present",
            headline="Task completed",
        )
    ]
    payload = report_to_dict(_report(harness="demo", tasks=[task]))
    row = payload["tasks"][0]
    assert row["check_kind"] == "builtin"
    assert row["check_answers"][0]["label"] == "Task completed"
    assert row["check_answers"][0]["answer"].startswith("Yes")


def test_format_cli_fresh_skip_judge_is_not_older_run() -> None:
    report = _report(
        harness="cursor-agent",
        config={
            "harness": "cursor-agent",
            "timeout_effective": 300,
            "judge": {"provider": "skip", "backend": "skip", "display_name": "Checks"},
        },
        tasks=[_task(judge={"status": "skip", "provider": "skip"})],
    )
    text = format_cli(report)
    assert "Older run (before live-only checks)" not in text
    assert "Cursor" in text


def test_format_cli_names_codex_default_model() -> None:
    report = _report(
        harness="codex",
        config={
            "harness": "codex",
            "model": "gpt-5.6-luna",
            "timeout_effective": 240,
            "applied": {"model": False},
        },
        tasks=[_task(judge=None)],
    )
    text = format_cli(report)
    assert "Codex" in text
    assert "luna" in text.lower()
    assert "Older run" not in text


def test_format_cli_shows_subscription_or_dollar_cost() -> None:
    sub = _report(
        harness="cursor-agent",
        config={"harness": "cursor-agent"},
        tasks=[
            _task(
                judge=None,
            )
        ],
    )
    sub.tasks[0].usage = {
        "tokens_total": 100,
        "agent_cost_label": SUBSCRIPTION_COST_LABEL,
    }
    text = format_cli(sub)
    assert SUBSCRIPTION_COST_LABEL in text
    paid = _report(
        harness="cursor-agent",
        config={"harness": "cursor-agent"},
        tasks=[_task(judge=None)],
    )
    paid.tasks[0].usage = {"tokens_total": 100, "cost_usd": 0.42}
    dollars = format_cli(paid)
    assert "$0.42" in dollars or "$0.420" in dollars


def test_report_json_includes_scored_by() -> None:
    report = _report(
        harness="demo",
        config={"judge": {"provider": "skip", "display_name": "Built-in checker"}},
        tasks=[_task(judge=None)],
    )
    payload = report_to_dict(report)
    assert payload["scored_by"] == "Quality was not scored."
