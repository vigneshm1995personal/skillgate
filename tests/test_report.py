from __future__ import annotations

from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.judge_openai import OUT_OF_CREDITS
from skillgate_ai.report import format_cli, report_to_dict, scored_by_line


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
        harness="llm",
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
    assert line.startswith("OpenAI couldn't score this run.")
    assert "out of credits" in line
    assert "scored this run" not in line
    text = format_cli(report)
    assert "OpenAI (your key) scored this run." not in text
    assert "couldn't score this run" in text


def test_scored_by_skip_on_live_does_not_deny_live_model() -> None:
    report = _report(
        harness="llm",
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
    assert line == "The skill ran live. The built-in checker scored it."
    assert "not a live model" not in line.lower()
    text = format_cli(report)
    assert "not a live model" not in text.lower()
    assert "ran live" in text


def test_scored_by_demo_still_says_not_a_live_model() -> None:
    report = _report(
        harness="demo",
        config={"judge": {"provider": "skip", "display_name": "Built-in checker"}},
        tasks=[_task(judge=None)],
    )
    assert scored_by_line(report) == (
        "Built-in checker scored this run. This is not a live model."
    )


def test_scored_by_openai_with_answers() -> None:
    report = _report(
        harness="llm",
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
    assert scored_by_line(report) == "OpenAI (your key) scored this run."


def test_report_json_includes_scored_by() -> None:
    report = _report(
        harness="demo",
        config={"judge": {"provider": "skip", "display_name": "Built-in checker"}},
        tasks=[_task(judge=None)],
    )
    payload = report_to_dict(report)
    assert payload["scored_by"] == (
        "Built-in checker scored this run. This is not a live model."
    )
