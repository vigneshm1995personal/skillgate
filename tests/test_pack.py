from __future__ import annotations

from pathlib import Path

from skillgate_ai.pack import (
    copy_skill_pack,
    fixture_files,
    list_pack_files,
    relevant_eval_fixtures,
    skill_pack_hash,
)

ROOT = Path(__file__).resolve().parents[1]


def _write_skill(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: A pack skill. Use when hashing goldens.\n"
        "---\n\n"
        f"# {name}\n",
        encoding="utf-8",
    )
    return folder


def test_list_pack_files_includes_goldens(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "notes", "notes")
    goldens = skill / "evals" / "goldens"
    goldens.mkdir(parents=True)
    (goldens / "complete.json").write_text("{}\n", encoding="utf-8")
    listed = {item["path"] for item in list_pack_files(skill)}
    assert "evals/goldens/complete.json" in listed


def test_copy_skill_pack_skips_goldens_by_default(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path / "notes", "notes")
    goldens = skill / "evals" / "goldens"
    goldens.mkdir(parents=True)
    (goldens / "complete.json").write_text("{}\n", encoding="utf-8")
    dest = tmp_path / "installed" / "notes"
    copy_skill_pack(skill, dest)
    assert not (dest / "evals" / "goldens").exists()


def test_copy_skill_pack_include_goldens_matches_recorded_pass_hash(tmp_path: Path) -> None:
    """Goldens are in the pass hash; deploy copies must ship the same files."""
    skill = _write_skill(tmp_path / "notes", "notes")
    goldens = skill / "evals" / "goldens"
    goldens.mkdir(parents=True)
    (goldens / "complete.json").write_text("{}\n", encoding="utf-8")
    recorded = skill_pack_hash(skill)
    skipped = tmp_path / "skipped" / "notes"
    copy_skill_pack(skill, skipped)
    assert skill_pack_hash(skipped) != recorded
    dest = tmp_path / "deploy" / "notes"
    copy_skill_pack(skill, dest, include_goldens=True)
    assert (dest / "evals" / "goldens" / "complete.json").is_file()
    assert skill_pack_hash(dest) == recorded


def test_fixture_files_and_relevant_eval_fixtures_seeded_pdf() -> None:
    pack = ROOT / "skills" / "pdf"
    fixtures = relevant_eval_fixtures(pack)
    assert fixtures
    names = {item["dest"] for item in fixtures}
    assert "hello.pdf" in names
    files = fixture_files(pack)
    assert any(item["path"].startswith("evals/") for item in files)


def test_list_pack_files_skips_missing_pack(tmp_path: Path) -> None:
    assert list_pack_files(tmp_path / "missing") == []
