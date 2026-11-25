from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.pack.pathsafe import (
    _safe_filename,
    implied_fixture_name,
    safe_relpath,
    try_resolve_pack_root,
)
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


def test_safe_relpath_rejects_parent_segments() -> None:
    with pytest.raises(ValueError, match="inside the skill folder"):
        safe_relpath("../escape.txt")


def test_safe_filename_rewrites_dotdot() -> None:
    assert _safe_filename("..") == "sample.txt"


def test_implied_fixture_name_detects_pdf_mentions() -> None:
    assert implied_fixture_name("rotate this PDF file").endswith(".pdf")


def test_try_resolve_pack_root_returns_none_for_missing_dir(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert try_resolve_pack_root(missing) is None
