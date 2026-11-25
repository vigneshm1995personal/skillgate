from __future__ import annotations

from pathlib import Path

from skillgate_ai.scorers import (
    RunArtifacts,
    Score,
    TriggerEvidence,
    headline_for,
    score_answer_contains,
    score_rubric,
    score_task_completion,
)
from skillgate_ai.suite import FileExpect, RubricCheck, TaskSpec


def test_headline_for_pass_fail_and_unknown() -> None:
    assert headline_for(Score(scorer="rubric", passed=True, detail="ok")) == "Rubric passed"
    assert (
        "mismatch"
        in headline_for(Score(scorer="answer_contains", passed=False, detail="missing")).lower()
    )
    assert headline_for(Score(scorer="custom", passed=False, detail="why")) == "why"


def test_score_answer_contains_reads_stdout_answer() -> None:
    artifacts = RunArtifacts(
        workspace=Path("/tmp/ws"),
        trigger=TriggerEvidence(selected_skill="pdf"),
        stdout='{"type":"result","result":"invoice total 42"}\n',
        stderr="",
    )
    score = score_answer_contains(["42"], artifacts)
    assert score.passed is True


def test_score_task_completion_requires_output_file(tmp_path: Path) -> None:
    expects = [FileExpect(path="output/result.txt", kind="text")]
    score = score_task_completion(expects, tmp_path)
    assert score.passed is False


def test_score_rubric_checks_workspace_file(tmp_path: Path) -> None:
    report = tmp_path / "output" / "report.txt"
    report.parent.mkdir(parents=True)
    report.write_text("hello world", encoding="utf-8")
    checks = [RubricCheck(id="r1", file="output/report.txt", contains="world")]
    score = score_rubric(checks, min_score=1.0, workspace=tmp_path)
    assert score.passed is True


def test_score_skill_trigger_uses_task_expectation(tmp_path: Path) -> None:
    task = TaskSpec(
        id="t1",
        prompt="Use the pdf skill",
        expect_skill="pdf",
        scorers=[],
    )
    from skillgate_ai.scorers import score_skill_trigger

    evidence = TriggerEvidence(selected_skill="pdf", transcript="read SKILL.md")
    score = score_skill_trigger(task, evidence, skills=[])
    assert score.scorer == "skill_trigger"
