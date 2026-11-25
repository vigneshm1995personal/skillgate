from __future__ import annotations

from pathlib import Path

import pytest

from skillgate_ai.ingest import (
    IngestError,
    Skill,
    canonical_skill_name,
    discover_skills,
    folder_matches_skill,
    folder_slug,
    ingest_skill,
    slugify_skill_name,
)

ROOT = Path(__file__).resolve().parents[1]


def test_slugify_and_folder_match() -> None:
    assert slugify_skill_name("CSV Cleaner") == "csv-cleaner"
    assert folder_matches_skill("csv-cleaner", "csv-cleaner") is True
    assert folder_matches_skill("pack", "pdf") is True


def test_canonical_skill_name_maps_generic_pack() -> None:
    skills = [Skill(path=Path("/x/pdf"), name="pdf", description="", body="")]
    assert canonical_skill_name("pack", skills) == "pdf"


def test_canonical_skill_name_resolves_folder_name() -> None:
    skills = [Skill(path=Path("/skills/pdf"), name="pdf", description="", body="")]
    assert canonical_skill_name("pdf", skills) == "pdf"


def test_folder_slug_from_path() -> None:
    assert folder_slug(Path("/skills/my-pack")) == "my-pack"


def test_discover_skills_finds_pdf_example() -> None:
    names = {skill.name for skill in discover_skills(ROOT / "skills")}
    assert "pdf" in names


def test_ingest_skill_requires_description(tmp_path: Path) -> None:
    pack = tmp_path / "bad"
    pack.mkdir()
    (pack / "SKILL.md").write_text("---\nname: bad\n---\n", encoding="utf-8")
    with pytest.raises(IngestError, match="description"):
        ingest_skill(pack)
