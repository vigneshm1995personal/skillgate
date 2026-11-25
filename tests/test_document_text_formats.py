from __future__ import annotations

from pathlib import Path

from skillgate_ai.document_text import extract_document_text


def test_extract_document_text_missing_file(tmp_path: Path) -> None:
    assert extract_document_text(tmp_path / "nope.pdf") is None


def test_extract_unsupported_binary_returns_none(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    path.write_bytes(b"\x00\x01\x02")
    assert extract_document_text(path) is None


def test_extract_document_text_caps_long_pdf(tmp_path: Path) -> None:
    from reportlab.pdfgen import canvas

    pdf = tmp_path / "long.pdf"
    c = canvas.Canvas(str(pdf))
    c.drawString(72, 800, "x" * 50)
    c.save()
    text = extract_document_text(pdf, limit=10)
    assert text is not None
    assert len(text) <= 10
