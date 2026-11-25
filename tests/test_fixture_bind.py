from __future__ import annotations

import pytest

from skillgate_ai.fixture_bind import (
    GateVerdict,
    _has_files,
    _prompt_for_file,
    _report_covers_pinned_ids,
    _template_check,
    _unique_id,
    authentic_completion_passed,
    coverage_required,
    decide_gate_result,
    is_completion_check,
    is_trigger_only,
)


@pytest.mark.parametrize(
    "check",
    [
        {"output_path": "o.txt"},
        {"contains": "x"},
        {"expected": "x"},
        {"golden_path": "g"},
    ],
)
def test_is_completion_check_detects_output_contains_or_golden(check) -> None:
    assert is_completion_check(check) is True


def test_is_completion_check_rejects_prompt_only() -> None:
    assert is_completion_check({"prompt": "p"}) is False


def test_is_trigger_only_excludes_negative_and_completion() -> None:
    assert is_trigger_only({"should_trigger": False}) is False
    assert is_trigger_only({"contains": "x"}) is False
    assert is_trigger_only({"prompt": "p"}) is True


def test_prompt_for_file_swaps_existing_filename() -> None:
    assert _prompt_for_file("Summarize report.pdf now", "evals/fixtures/a.pdf") == (
        "Summarize evals/fixtures/a.pdf now"
    )


def test_prompt_for_file_prefixes_read_when_no_filename() -> None:
    assert _prompt_for_file("Summarize it", "a.txt") == "Read a.txt, summarize it."


def test_prompt_for_file_empty_template_uses_default_output() -> None:
    assert _prompt_for_file("", "a.txt") == "Read a.txt and save the result to output/result.txt."


def test_unique_id_appends_counter() -> None:
    assert _unique_id("Complete Report", {"complete-report", "complete-report-2"}) == (
        "complete-report-3"
    )
    assert _unique_id("!!!", set()) == "complete"


@pytest.mark.parametrize(
    ("files", "expected"),
    [
        ([{"src": "a"}], False),
        ([{"src": "a", "dest": "b"}], True),
        ("x", False),
        ([], False),
    ],
)
def test_has_files_requires_src_and_dest(files, expected) -> None:
    assert _has_files(files) is expected


def test_template_check_falls_back_to_default_prompt() -> None:
    result = dict(_template_check([{"should_trigger": False}], "desc"))
    assert result == {
        "prompt": "Read the input and save the result to output/result.txt.",
        "should_trigger": True,
        "output_path": "output/result.txt",
        "contains": "desc",
    }


def test_decide_gate_result_status_branches() -> None:
    assert decide_gate_result(
        harness=None, passed=None, status="running"
    ) == GateVerdict("pending", "Evaluation is still running.")
    assert decide_gate_result(harness=None, passed=None, status="error") == GateVerdict(
        "blocked", "This run ended in error."
    )
    assert decide_gate_result(harness=None, passed=True, status="done") == GateVerdict(
        "blocked", "Deploy needs a live harness."
    )
    assert decide_gate_result(harness="cursor-agent", passed=False, status="done") == GateVerdict(
        "blocked", "Get a passing run to unlock Deploy."
    )


def test_report_covers_pinned_ids() -> None:
    report = {"tasks": [{"id": "a"}, {"id": "b"}]}
    assert _report_covers_pinned_ids(report, ("a",)) is True
    assert _report_covers_pinned_ids(report, ("c",)) is False
    assert _report_covers_pinned_ids(report, ()) is False


def test_coverage_required_from_report_files() -> None:
    report = {"tasks": [{"files": [{"src": "a", "dest": "b"}]}]}
    assert coverage_required(None, report=report) is True
    assert coverage_required(None) is False


def test_authentic_completion_passed_requires_task_completion_score() -> None:
    report = {
        "tasks": [
            {
                "passed": True,
                "scores": [{"scorer": "rubric", "passed": True}],
            }
        ]
    }
    assert authentic_completion_passed(None, report) is False
