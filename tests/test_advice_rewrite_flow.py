from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from skillgate_ai.advice.rewrite import (
    apply_description_fix,
    description_from_paste,
    rewrite_skill_description,
)
from skillgate_ai.pack.pathsafe import _path_under_skill

ROOT = Path(__file__).resolve().parents[1]


def test_rewrite_skill_description_updates_frontmatter(tmp_path: Path) -> None:
    pack = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", pack)
    skill_md = pack / "SKILL.md"
    before = skill_md.read_text(encoding="utf-8")
    rewrite_skill_description(skill_md, "Updated PDF description for tests.")
    after = skill_md.read_text(encoding="utf-8")
    assert "Updated PDF description" in after
    assert before != after


def test_description_from_paste_requires_description_key() -> None:
    text = "---\nname: x\ndescription: from paste\n---\n"
    assert description_from_paste(text) == "from paste"


def test_description_from_paste_accepts_frontmatter_without_trailing_newline() -> None:
    text = "---\nname: x\ndescription: trimmed\n---"
    assert description_from_paste(text) == "trimmed"
    with pytest.raises(ValueError):
        description_from_paste("---\nname: x\n---\n")


def test_apply_description_fix_restores_scripts_from_donor(tmp_path: Path) -> None:
    source = tmp_path / "pdf"
    donor = tmp_path / "donor"
    shutil.copytree(ROOT / "skills" / "pdf", source)
    shutil.copytree(ROOT / "skills" / "pdf", donor)
    shutil.rmtree(source / "scripts")
    dest_root = tmp_path / "work"
    out = apply_description_fix(
        source=source,
        dest_root=dest_root,
        new_description="With scripts from donor.",
        restore_scripts_from=donor,
    )
    assert (out / "scripts").is_dir()


def test_rewrite_skill_description_requires_skill_md_filename(tmp_path: Path) -> None:
    other = tmp_path / "README.md"
    other.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Expected SKILL.md"):
        rewrite_skill_description(other, "desc")


def test_working_folder_destination_uses_pack_containment(tmp_path: Path) -> None:
    dest_root = tmp_path / "work"
    dest_root.mkdir()
    assert _path_under_skill(dest_root, "..") is None
    assert _path_under_skill(dest_root, "nested/../escape") is None
    allowed = _path_under_skill(dest_root, "pdf-copy")
    assert allowed is not None
    assert allowed.parent == dest_root.resolve()


def test_description_from_paste_rejects_non_mapping_frontmatter() -> None:
    text = "---\nnot a mapping\n---\n"
    with pytest.raises(ValueError, match="frontmatter"):
        description_from_paste(text)


def test_apply_description_fix_updates_pack_in_place(tmp_path: Path) -> None:
    source = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", source)
    out = apply_description_fix(
        source=source,
        dest_root=tmp_path,
        new_description="In-place description update.",
    )
    assert out.resolve() == source.resolve()
    assert "In-place description update." in (out / "SKILL.md").read_text(encoding="utf-8")


def test_apply_description_fix_copies_pack(tmp_path: Path) -> None:
    source = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", source)
    dest_root = tmp_path / "work"
    out = apply_description_fix(
        source=source,
        dest_root=dest_root,
        new_description="Copied pack description.",
    )
    assert out.is_dir()
    assert (out / "SKILL.md").is_file()
    body = (out / "SKILL.md").read_text(encoding="utf-8")
    assert "Copied pack description" in body


def test_apply_description_fix_replaces_stale_destination_copy(tmp_path: Path) -> None:
    source = tmp_path / "pdf"
    shutil.copytree(ROOT / "skills" / "pdf", source)
    dest_root = tmp_path / "work"
    dest_root.mkdir()
    stale = dest_root / "pdf"
    stale.mkdir()
    (stale / "STALE.txt").write_text("old", encoding="utf-8")
    out = apply_description_fix(
        source=source,
        dest_root=dest_root,
        new_description="Replaced stale copy.",
    )
    assert not (out / "STALE.txt").exists()
    assert "Replaced stale copy." in (out / "SKILL.md").read_text(encoding="utf-8")
