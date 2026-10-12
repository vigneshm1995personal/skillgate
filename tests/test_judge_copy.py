from __future__ import annotations

from skillgate_ai.engine import SuiteReport, TaskReport
from skillgate_ai.judge_copy import customer_scorer_name, scored_by_phrase
from skillgate_ai.report import scored_by_line


def _task(*, judge: dict | None, passed: bool = True) -> TaskReport:
    return TaskReport(
        task_id="t1",
        prompt="p",
        expect_skill="pdf",
        passed=passed,
        scores=[],
        selected_skill="pdf",
        failures=[] if passed else ["failed"],
        judge=judge,
    )


def _report(*, tasks: list[TaskReport], config: dict | None = None, harness: str = "llm") -> SuiteReport:
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


def test_auto_openai_copy_says_the_judge() -> None:
    assert customer_scorer_name({"provider": "openai", "chosen": "false"}) == "the judge"
    assert scored_by_phrase("the judge") == "Scored by the judge"
    report = _report(
        config={"judge": {"provider": "openai", "display_name": "the judge", "chosen": "false"}},
        tasks=[
            _task(
                judge={
                    "status": "completed",
                    "provider": "openai",
                    "display_name": "the judge",
                    "chosen": "false",
                    "answers": {"task_completion": {"choice": "Fully completed"}},
                }
            )
        ],
    )
    assert scored_by_line(report) == "Scored by the judge"
    assert "Decisions" not in scored_by_line(report)
    assert "OpenAI" not in scored_by_line(report)


def test_chosen_provider_is_named() -> None:
    assert customer_scorer_name({"provider": "openai", "chosen": "true"}) == "OpenAI"
    assert customer_scorer_name({"provider": "jev", "chosen": True}) == "Jev"
    assert customer_scorer_name({"provider": "jev"}) == "Jev"
    assert customer_scorer_name({"provider": "aws", "chosen": "true"}) == "AWS"
    assert customer_scorer_name({"provider": "compatible", "chosen": "true"}) == "Other"
    assert customer_scorer_name({"display_name": "Other"}) == "Other"
    assert customer_scorer_name({"display_name": "Jev", "chosen": True}) == "Jev"
    assert customer_scorer_name({"display_name": "OpenAI", "chosen": True}) == "OpenAI"
    report = _report(
        config={"judge": {"provider": "jev", "display_name": "Jev", "chosen": "true"}},
        tasks=[
            _task(
                judge={
                    "status": "completed",
                    "provider": "jev",
                    "display_name": "Jev",
                    "chosen": "true",
                    "answers": {"task_completion": {"choice": "Fully completed"}},
                }
            )
        ],
    )
    assert scored_by_line(report) == "Scored by Jev"


def test_auto_error_does_not_name_openai() -> None:
    report = _report(
        config={"judge": {"provider": "openai", "display_name": "the judge", "chosen": "false"}},
        tasks=[
            _task(
                passed=False,
                judge={
                    "status": "error",
                    "provider": "openai",
                    "display_name": "the judge",
                    "chosen": "false",
                    "answers": {},
                    "reasons": ["The judge did not accept this API key."],
                },
            )
        ],
    )
    line = scored_by_line(report)
    assert line.startswith("The judge couldn't score this run.")
    assert "OpenAI" not in line
    assert "Decisions" not in line


def test_legacy_openai_display_name_does_not_leak_decisions() -> None:
    report = _report(
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
    assert scored_by_line(report) == "Scored by the judge"
