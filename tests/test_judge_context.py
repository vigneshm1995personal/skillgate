from __future__ import annotations

from pathlib import Path

from reportlab.pdfgen import canvas

from skillgate_ai.document_text import extract_document_text
from skillgate_ai.judge_context import build_agent_trajectory, enrich_output_row
from skillgate_ai.judge_openai import _artifacts_without_bodies, _state_text
from skillgate_ai.scorers import Score
from skillgate_ai.spans import make_span


def test_extract_pdf_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "memo.pdf"
    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 800, "Invoice total 42.50")
    c.save()
    text = extract_document_text(pdf_path)
    assert text and "42.50" in text


def test_enrich_output_row_attaches_pdf_text(tmp_path: Path) -> None:
    pdf_path = tmp_path / "output" / "out.pdf"
    pdf_path.parent.mkdir(parents=True)
    c = canvas.Canvas(str(pdf_path))
    c.drawString(72, 800, "Q3 revenue up")
    c.save()
    row = {"path": "output/out.pdf", "present": True, "kind": "bytes", "size": 1}
    enriched = enrich_output_row(row, pdf_path)
    body = enriched.get("extracted_text") or enriched.get("body") or ""
    assert "Q3 revenue" in body


def test_extract_docx_text(tmp_path: Path) -> None:
    from docx import Document

    docx_path = tmp_path / "memo.docx"
    document = Document()
    document.add_paragraph("Meeting notes: ship the fix with tests.")
    document.save(str(docx_path))
    text = extract_document_text(docx_path)
    assert text and "tests" in text


def test_build_agent_trajectory_includes_commands() -> None:
    span = make_span(
        name="tool.shell",
        trace_id="t",
        attributes={"gen_ai.tool.name": "shell", "gen_ai.tool.call.arguments": "pytest -q"},
    )
    trajectory = build_agent_trajectory(
        spans=[span],
        transcript='{"type":"result","result":"done"}\npytest -q ... passed',
        path={"steps": 1, "errors": 0, "had_path": True},
        scores=[Score(scorer="skill_trigger", passed=True, detail="ok")],
    )
    assert trajectory["step_count"] == 1
    assert trajectory["commands"][0]["tool"] == "shell"
    assert trajectory["test_mentions"]


def test_state_text_includes_skill_and_trajectory() -> None:
    payload = _state_text(
        {
            "check_prompt": "Write a memo",
            "skill_instructions": "# memo\nAlways add tests first.",
            "agent_trajectory": {"commands": [{"kind": "tool.shell"}]},
            "artifacts": [],
        }
    )
    assert "skill_instructions" in payload
    assert "agent_trajectory" in payload
    assert "Always add tests" in payload


def test_artifacts_without_bodies_includes_extracted_text() -> None:
    rows = _artifacts_without_bodies(
        [{"path": "output/a.pdf", "present": True, "extracted_text": "hello pdf"}]
    )
    assert rows[0]["extracted_text"] == "hello pdf"
