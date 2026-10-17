"""Bundled demo PDFs for the pdf eval suite."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def _stale_example_marker(fixtures_dir: Path) -> bool:
    """A copied pdf example marker must not seed those PDFs into another skill."""
    if fixtures_dir.name != "fixtures":
        return False
    skill_root = fixtures_dir.parent.parent
    marker = skill_root / "evals" / ".skillgate-example"
    if not marker.is_file():
        return False
    try:
        slug = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return bool(slug) and slug != skill_root.name


def ensure_demo_pdfs(fixtures_dir: Path) -> None:
    if _stale_example_marker(fixtures_dir):
        return
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
