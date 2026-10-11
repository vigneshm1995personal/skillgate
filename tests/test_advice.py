from __future__ import annotations

from pathlib import Path

from skillgate_ai.advice import advise_task
from skillgate_ai.ingest import Skill
from skillgate_ai.scorers import Score
from skillgate_ai.suite import FileExpect, ScorerSpec, TaskSpec

PDF = Skill(
    path=Path("skills/pdf"),
    name="pdf",
    description="Extract text from PDFs to output/extracted.txt. Create and merge PDFs.",
    body=(
        "# Steps\n"
        "1. Extract text to output/extracted.txt.\n"
        "2. Create a PDF at output/status.pdf.\n"
    ),
)


def _create_status_task() -> TaskSpec:
    return TaskSpec(
        id="create-status",
        prompt='Create a PDF at output/status.pdf titled Q3 Status that contains "All systems are go."',
        expect_skill="pdf",
        scorers=[
            ScorerSpec(
                type="task_completion",
                files=[FileExpect(path="output/status.pdf")],
            )
        ],
    )


def test_advise_nonzero_exit_does_not_suggest_another_check_path() -> None:
    scores = [
        Score(
            scorer="task_completion",
            passed=False,
            detail="missing output/status.pdf",
            headline="Task not completed",
        )
    ]
    advice = advise_task(
        _create_status_task(),
        scores,
        PDF,
        "pdf",
        returncode=2,
        stderr=(
            "usage: create_pdf.py [-h] [--title TITLE] [--body BODY] output\n"
            'create_pdf.py: error: unrecognized arguments: Status"\n'
        ),
    )
    assert advice is not None
    blob = f"{advice.headline} {advice.why} {advice.change}"
    assert "extracted.txt" not in blob
    assert "output_path" not in blob.lower()
    assert "2" in blob
    assert "unrecognized arguments" in blob.lower() or "failed" in blob.lower()


def test_advise_ignores_agent_jsonl_stderr() -> None:
    scores = [
        Score(
            scorer="task_completion",
            passed=False,
            detail="missing output/status.pdf",
            headline="Task not completed",
        )
    ]
    advice = advise_task(
        _create_status_task(),
        scores,
        PDF,
        "pdf",
        returncode=1,
        stderr='{"type":"error","message":"turn failed"}\n',
    )
    assert advice is not None
    assert advice.headline != "The command failed"
    assert "extracted.txt" not in f"{advice.headline} {advice.why} {advice.change}"
