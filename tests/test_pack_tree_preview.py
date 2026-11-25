from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.pack.tree import pack_file_path, pack_preview

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "skills" / "pdf"


def test_pack_file_path_resolves_skill_md() -> None:
    path = pack_file_path(PDF, "SKILL.md")
    assert path.is_file()
    assert path.name == "SKILL.md"


def test_pack_file_path_missing_raises() -> None:
    with pytest.raises(FileNotFoundError):
        pack_file_path(PDF, "evals/fixtures/does-not-exist.bin")


def test_pack_preview_classifies_pdf_fixture() -> None:
    preview = pack_preview(PDF, "evals/fixtures/hello.pdf")
    assert preview["kind"] == "pdf"
    assert preview["bytes"] > 0


def test_pack_preview_skill_md_is_text() -> None:
    preview = pack_preview(PDF, "SKILL.md")
    assert preview["kind"] == "text"
    assert "description" in (preview.get("text") or "").lower()
