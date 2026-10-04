"""Bundled demo PDFs for the pdf eval suite."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def ensure_demo_pdfs(fixtures_dir: Path) -> None:
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    specs = {
        "hello.pdf": "Hello Skill Gate",
        "invoice.pdf": "Invoice #1042 — Amount due $40",
        "alpha.pdf": "Alpha page",
        "beta.pdf": "Beta page",
        "notes.pdf": "Meeting notes: ship the skill gate demo.",
    }
    for name, text in specs.items():
        path = fixtures_dir / name
        if path.is_file() and path.stat().st_size > 0:
            continue
        write_pdf(path, text)


def write_pdf(path: Path, text: str) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    width, height = letter
    c.setFont("Times-Roman", 18)
    c.drawString(72, height - 108, text)
    c.save()
