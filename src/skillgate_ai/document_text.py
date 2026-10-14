"""Extract plain text from common agent output formats for scoring."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.pack_files import GOLDEN_TAIL_CHARS

_TEXT_SUFFIXES = frozenset({".pdf", ".docx", ".xlsx"})


def extract_document_text(path: Path, *, limit: int = GOLDEN_TAIL_CHARS) -> str | None:
    """Best-effort text from PDF, Word, or Excel outputs. Returns None when unsupported."""
    if not path.is_file():
        return None
    suffix = path.suffix.lower()
    if suffix not in _TEXT_SUFFIXES and suffix not in {".xlsm"}:
        # Still try PDF magic when sniffed as generic bytes.
        try:
            head = path.read_bytes()[:8]
        except OSError:
            return None
        if not head.startswith(b"%PDF"):
            return None
    try:
        if suffix == ".docx" or _is_zip_docx(path):
            return _cap(_docx_text(path), limit=limit)
        if suffix in {".xlsx", ".xlsm"}:
            return _cap(_xlsx_text(path), limit=limit)
        return _cap(_pdf_text(path), limit=limit)
    except Exception:
        return None


def _cap(text: str | None, *, limit: int) -> str | None:
    if not text or not str(text).strip():
        return None
    cleaned = str(text).strip()
    if limit <= 0 or len(cleaned) <= limit:
        return cleaned
    return cleaned[-limit:]


def _is_zip_docx(path: Path) -> bool:
    try:
        return path.read_bytes()[:2] == b"PK"
    except OSError:
        return False


def _pdf_text(path: Path) -> str | None:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    parts = [(page.extract_text() or "") for page in reader.pages]
    joined = "\n".join(parts).strip()
    return joined or None


def _docx_text(path: Path) -> str | None:
    from docx import Document

    document = Document(str(path))
    parts = [para.text for para in document.paragraphs if para.text.strip()]
    joined = "\n".join(parts).strip()
    return joined or None


def _xlsx_text(path: Path) -> str | None:
    from openpyxl import load_workbook

    workbook = load_workbook(filename=str(path), read_only=True, data_only=True)
    rows: list[str] = []
    for sheet in workbook.worksheets:
        for row in sheet.iter_rows(values_only=True):
            cells = [str(cell).strip() for cell in row if cell is not None and str(cell).strip()]
            if cells:
                rows.append("\t".join(cells))
    workbook.close()
    joined = "\n".join(rows).strip()
    return joined or None
