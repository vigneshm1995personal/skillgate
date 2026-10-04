from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.errors import IngestError
from skillgate_ai.ingest import discover_skills, ingest_skill


def test_good_pdf_skill(project_root: Path) -> None:
    skill = ingest_skill(project_root / "skills" / "pdf")
    assert skill.name == "pdf"
    assert "pdf" in skill.description.lower()


def test_name_must_match_folder(tmp_path: Path) -> None:
    folder = tmp_path / "other"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: Does a thing when you ask.\n---\n\n# Hi\n",
        encoding="utf-8",
    )
    with pytest.raises(IngestError, match="must match"):
        ingest_skill(folder)


def test_generic_pack_mount_allows_skill_name(tmp_path: Path) -> None:
    """Docker/Compose bind-mount the skill at /pack; name stays the SKILL.md name."""
    folder = tmp_path / "pack"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: pdf\ndescription: Process PDF files for extract/merge/rotate.\n---\n",
        encoding="utf-8",
    )
    skill = ingest_skill(folder)
    assert skill.name == "pdf"
    assert skill.path == folder.resolve()


def test_missing_frontmatter(tmp_path: Path) -> None:
    folder = tmp_path / "nope"
    folder.mkdir()
    (folder / "SKILL.md").write_text("# just markdown\n", encoding="utf-8")
    with pytest.raises(IngestError, match="frontmatter"):
        ingest_skill(folder)


def test_bad_name_hyphens(tmp_path: Path) -> None:
    folder = tmp_path / "pdf--x"
    folder.mkdir()
    (folder / "SKILL.md").write_text(
        "---\nname: pdf--x\ndescription: Bad name on purpose for ingest.\n---\n",
        encoding="utf-8",
    )
    with pytest.raises(IngestError, match="invalid"):
        ingest_skill(folder)


def test_discover_missing_dir_raises(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="skills/ folder not found"):
        discover_skills(tmp_path / "skills")


def test_discover_empty_dir_raises(tmp_path: Path) -> None:
    (tmp_path / "skills").mkdir()
    with pytest.raises(IngestError, match="No SKILL.md folders"):
        discover_skills(tmp_path / "skills")
