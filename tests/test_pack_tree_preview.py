from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.pack.pathsafe import (
    _safe_filename,
    fixture_src_for,
    implied_fixture_name,
    is_pack_relative,
    resolve_pack_root,
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


def test_resolve_pack_root_requires_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "not-a-dir"
    file_path.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Skill folder not found"):
        resolve_pack_root(file_path)


def test_safe_relpath_maps_bare_filename_into_fixtures() -> None:
    assert safe_relpath("hello.csv").endswith("hello.csv")
    assert safe_relpath("SKILL.md") == "SKILL.md"


def test_is_pack_relative_rejects_absolute_paths() -> None:
    assert is_pack_relative("/etc/passwd") is False
    assert is_pack_relative("evals/fixtures/x.pdf") is True


def test_fixture_src_for_uses_dest_name() -> None:
    assert fixture_src_for("ignored", dest="out/report.csv").endswith("report.csv")


def test_implied_fixture_name_picks_csv_json_and_image_hints() -> None:
    assert implied_fixture_name("edit this CSV").endswith(".csv")
    assert implied_fixture_name("return JSON").endswith(".json")
    assert implied_fixture_name("from this screenshot").endswith(".png")
