from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.scorers import (
    RunArtifacts,
    Score,
    ScorerSpec,
    TriggerEvidence,
    headline_for,
    score_answer_contains,
    score_one,
    score_rubric,
    score_task,
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


def test_score_skill_trigger_fails_wrong_skill() -> None:
    from skillgate_ai.scorers import score_skill_trigger

    task = TaskSpec(id="t", prompt="Use csv", expect_skill="csv-cleaner", scorers=[])
    evidence = TriggerEvidence(selected_skill="pdf", transcript="")
    score = score_skill_trigger(task, evidence, skills=[])
    assert score.passed is False
    assert score.actual == "pdf"


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


def test_score_task_completion_passes_with_contains(tmp_path: Path) -> None:
    target = tmp_path / "output" / "result.txt"
    target.parent.mkdir(parents=True)
    target.write_text("done ok", encoding="utf-8")
    expects = [
        FileExpect(path="output/result.txt", kind="text", contains="done", min_bytes=3),
    ]
    score = score_task_completion(expects, tmp_path)
    assert score.passed is True


def test_score_task_skips_output_scorers_when_no_expect_skill(tmp_path: Path) -> None:
    task = TaskSpec(
        id="neg",
        prompt="no skill",
        expect_skill=None,
        scorers=[
            ScorerSpec(type="task_completion", files=[FileExpect(path="output/x.txt")]),
            ScorerSpec(type="skill_trigger"),
        ],
    )
    artifacts = RunArtifacts(
        workspace=tmp_path,
        trigger=TriggerEvidence(selected_skill=None),
    )
    scores = score_task(task, artifacts)
    assert len(scores) == 1
    assert scores[0].scorer == "skill_trigger"


def test_score_one_unknown_scorer_reports_detail() -> None:
    spec = ScorerSpec.model_construct(type="mystery")
    task = TaskSpec(id="t", prompt="p", scorers=[])
    artifacts = RunArtifacts(workspace=Path("/tmp"), trigger=TriggerEvidence(selected_skill=None))
    score = score_one(spec, task, artifacts)
    assert score.passed is False
    assert "Unknown scorer" in (score.detail or "")


@pytest.mark.parametrize(
    ("score", "snippet"),
    [
        (
            Score(scorer="skill_trigger", passed=True, expected="none", detail="ok"),
            "did not trigger",
        ),
        (Score(scorer="task_completion", passed=True, detail="ok"), "completed"),
        (Score(scorer="tool_calls", passed=False, detail="a; b"), "a (+1 more)"),
        (Score(scorer="consequential_calls", passed=True, detail="ok"), "consequential"),
    ],
)
def test_headline_for_scorer_branches(score: Score, snippet: str) -> None:
    assert snippet.lower() in headline_for(score).lower()


def test_score_rubric_pdf_page_count(tmp_path: Path) -> None:
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "output" / "report.pdf"
    pdf.parent.mkdir(parents=True)
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 800, "page1")
    c.showPage()
    c.drawString(72, 800, "page2")
    c.save()
    checks = [RubricCheck(id="p", file="output/report.pdf", pdf_pages=2)]
    score = score_rubric(checks, min_score=1.0, workspace=tmp_path)
    assert score.passed is True


def test_score_task_runs_all_scorers(tmp_path: Path) -> None:
    task = TaskSpec(
        id="t",
        prompt="p",
        expect_skill="pdf",
        scorers=[
            ScorerSpec(type="skill_trigger"),
            ScorerSpec(
                type="answer_contains",
                answer=["hello"],
            ),
        ],
    )
    artifacts = RunArtifacts(
        workspace=tmp_path,
        trigger=TriggerEvidence(selected_skill="pdf"),
        stdout='{"type":"result","result":"hello"}\n',
    )
    scores = score_task(task, artifacts)
    assert len(scores) == 2
    assert all(s.headline for s in scores)


def test_score_answer_contains_empty_needles_is_zero_weight() -> None:
    artifacts = RunArtifacts(workspace=Path("/tmp"), trigger=TriggerEvidence(selected_skill=None))
    score = score_answer_contains([], artifacts)
    assert score.passed is True
    assert score.weight == 0
