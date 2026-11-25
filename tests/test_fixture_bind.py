from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.fixture_bind import (
    GateVerdict,
    _has_files,
    _prompt_for_file,
    _report_covers_pinned_ids,
    _template_check,
    _unique_id,
    apply_inherit,
    authentic_completion_passed,
    coverage_required,
    decide_gate,
    decide_gate_result,
    expand_from_folder,
    file_copies,
    is_completion_check,
    is_negative_check,
    is_trigger_only,
)

ROOT = Path(__file__).resolve().parents[1]
PDF_SKILL = ROOT / "skills" / "pdf"


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
    assert decide_gate_result(harness=None, passed=None, status="running") == GateVerdict(
        "pending", "Evaluation is still running."
    )
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


def test_is_negative_check_reads_should_trigger() -> None:
    assert is_negative_check({"should_trigger": False}) is True
    assert is_negative_check({"should_trigger": True}) is False


def test_file_copies_maps_fixture_src_dest() -> None:
    fixtures = [{"src": "evals/fixtures/a.pdf", "dest": "a.pdf"}]
    assert file_copies(fixtures) == [{"src": "evals/fixtures/a.pdf", "dest": "a.pdf"}]


def test_apply_inherit_injects_pack_fixtures_into_completion_checks() -> None:
    checks = [{"prompt": "Complete", "contains": "done", "output_path": "output/x.txt"}]
    out = apply_inherit(PDF_SKILL, checks, inherit=True)
    assert out[0].get("files")
    assert out[0].get("needs_upload") is False


def test_apply_inherit_skips_when_inherit_false() -> None:
    checks = [{"prompt": "Complete", "contains": "done", "output_path": "output/x.txt"}]
    out = apply_inherit(PDF_SKILL, checks, inherit=False)
    assert "files" not in out[0]


def test_expand_from_folder_creates_completion_rows_from_fixtures() -> None:
    existing = [{"prompt": "When user asks", "should_trigger": True}]
    out = expand_from_folder(PDF_SKILL, existing, description="PDF tasks")
    completion_ids = [item.get("id") for item in out if item.get("output_path")]
    assert len(completion_ids) >= 1
    assert any(item.get("files") for item in out)


def test_prompt_for_file_when_dest_already_in_prompt() -> None:
    dest = "evals/fixtures/hello.pdf"
    assert _prompt_for_file(f"Open {dest}", dest) == f"Open {dest}"


def test_prompt_for_file_capitalizes_read_line() -> None:
    text = _prompt_for_file("summarize the file", "in.csv")
    assert text.startswith("Read in.csv")
    assert text.endswith(".")


def test_template_check_prefers_existing_completion_row() -> None:
    checks = [
        {"prompt": "trig", "should_trigger": True},
        {"contains": "x", "output_path": "custom/out.txt"},
    ]
    assert _template_check(checks, "desc")["output_path"] == "custom/out.txt"


def test_coverage_required_when_pack_has_fixtures() -> None:
    assert coverage_required(PDF_SKILL) is True


def test_authentic_completion_passed_with_on_disk_fixture() -> None:
    report = {
        "tasks": [
            {
                "passed": True,
                "scores": [{"scorer": "task_completion", "passed": True}],
                "files": [{"src": "evals/fixtures/hello.pdf", "dest": "hello.pdf"}],
            }
        ]
    }
    assert authentic_completion_passed(PDF_SKILL, report) is True


def test_decide_gate_returns_decision_string() -> None:
    assert decide_gate(harness=None, passed=None, status="running") == "pending"


def test_decide_gate_warnings_when_fingerprint_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    from skillgate_ai import harness

    monkeypatch.setattr(harness, "is_live_harness", lambda name: name == "cursor-agent")
    trust = __import__(
        "skillgate_ai.case_pack",
        fromlist=["trust_suite_for_skill"],
    ).trust_suite_for_skill(PDF_SKILL)
    assert trust is not None
    verdict = decide_gate_result(
        harness="cursor-agent",
        passed=True,
        status="done",
        skill_path=PDF_SKILL,
        report={
            "tasks": [{"id": trust.case_ids[0]}],
            "pack_fingerprint": "deadbeef00000000",
        },
    )
    assert verdict.decision == "cleared"
    assert any("Dataset" in item for item in verdict.warnings)


def test_decide_gate_cleared_when_live_harness_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    from skillgate_ai import harness

    monkeypatch.setattr(harness, "is_live_harness", lambda name: name == "cursor-agent")
    verdict = decide_gate_result(
        harness="cursor-agent",
        passed=True,
        status="done",
        skill_path=PDF_SKILL,
        report={"tasks": [], "pack_fingerprint": ""},
    )
    assert verdict.decision == "cleared"
    assert verdict.reason == "This Dataset passed."
