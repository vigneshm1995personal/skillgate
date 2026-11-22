from __future__ import annotations

import os
from pathlib import Path

import pytest

from skillgate_ai.catalog import catalog_entries, find_skill
from skillgate_ai.errors import SkillGateError
from skillgate_ai.skill_md import write_skill_md


@pytest.fixture(autouse=True)
def _isolate_agent_skills(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(tmp_path / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(tmp_path / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(tmp_path / "claude-skills"))


def _symlink(src: Path, dest: Path) -> None:
    try:
        os.symlink(src, dest)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks not supported here: {exc}")


def _workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "project"
    (workspace / "skills").mkdir(parents=True)
    return workspace


def test_catalog_entries_skips_symlinked_dir_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside" / "evil"
    write_skill_md(outside, name="evil", description="Outside.", body="# X\n")
    root = _workspace(tmp_path)
    _symlink(outside, root / "skills" / "evil")
    assert all(e.get("slug") != "evil" for e in catalog_entries(root))
    assert all(e.get("slug") != "evil" for e in catalog_entries(root, include_agents=True))


def test_catalog_entries_skips_symlinked_skill_md_outside_root(tmp_path: Path) -> None:
    outside_md = tmp_path / "outside" / "SKILL.md"
    outside_md.parent.mkdir(parents=True)
    outside_md.write_text(
        "---\nname: evil\ndescription: Outside.\n---\n# SECRET\n",
        encoding="utf-8",
    )
    root = _workspace(tmp_path)
    evil = root / "skills" / "evil"
    evil.mkdir()
    _symlink(outside_md, evil / "SKILL.md")
    assert all(e.get("slug") != "evil" for e in catalog_entries(root))


def test_catalog_entries_keeps_symlink_inside_root(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    real = root / "shared" / "alias"
    write_skill_md(real, name="alias", description="Alias.", body="# Alias\n")
    _symlink(real, root / "skills" / "alias")
    entries = catalog_entries(root)
    matched = [e for e in entries if e.get("slug") == "alias"]
    assert len(matched) == 1
    assert matched[0]["source"] == "workspace"
    assert matched[0]["absolute"] == str(real.resolve())


def test_catalog_entries_skips_root_skill_md_outside_root(tmp_path: Path) -> None:
    outside_md = tmp_path / "outside" / "SKILL.md"
    outside_md.parent.mkdir(parents=True)
    outside_md.write_text(
        "---\nname: rootpack\ndescription: Outside.\n---\n",
        encoding="utf-8",
    )
    root = tmp_path / "project"
    root.mkdir()
    _symlink(outside_md, root / "SKILL.md")
    assert catalog_entries(root) == []


def test_catalog_entries_dedupes_alias_and_target(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    real = root / "skills" / "real"
    write_skill_md(real, name="real", description="Real.", body="# Real\n")
    _symlink(real, root / "skills" / "alias")
    slugs = [e.get("slug") for e in catalog_entries(root)]
    assert slugs.count("real") == 1
    assert "alias" not in slugs


def test_find_skill_plain_name_rejects_symlink_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside" / "evil"
    write_skill_md(outside, name="evil", description="Outside.", body="# X\n")
    root = _workspace(tmp_path)
    _symlink(outside, root / "skills" / "evil")
    with pytest.raises(SkillGateError, match="not found"):
        find_skill(root, "evil")


def test_find_skill_relative_path_rejects_symlink_outside_root(tmp_path: Path) -> None:
    outside = tmp_path / "outside" / "evil"
    write_skill_md(outside, name="evil", description="Outside.", body="# X\n")
    root = _workspace(tmp_path)
    _symlink(outside, root / "skills" / "evil")
    with pytest.raises(SkillGateError, match="outside this project"):
        find_skill(root, "skills/evil")


def test_find_skill_path_rejects_skill_md_outside_root(tmp_path: Path) -> None:
    outside_md = tmp_path / "outside" / "SKILL.md"
    outside_md.parent.mkdir(parents=True)
    outside_md.write_text(
        "---\nname: evil\ndescription: Outside.\n---\n",
        encoding="utf-8",
    )
    root = _workspace(tmp_path)
    evil = root / "skills" / "evil"
    evil.mkdir()
    _symlink(outside_md, evil / "SKILL.md")
    with pytest.raises(SkillGateError, match="not found"):
        find_skill(root, "skills/evil")


def test_find_skill_plain_name_allows_symlink_inside_root(tmp_path: Path) -> None:
    root = _workspace(tmp_path)
    real = root / "shared" / "alias"
    write_skill_md(real, name="alias", description="Alias.", body="# Alias\n")
    _symlink(real, root / "skills" / "alias")
    assert find_skill(root, "alias") == real.resolve()


def test_find_skill_agent_skill_unaffected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cursor_root = tmp_path / "cursor-skills"
    cursor_root.mkdir(parents=True)
    agentonly = cursor_root / "agentonly"
    write_skill_md(agentonly, name="agentonly", description="Agent.", body="# Agent\n")
    root = _workspace(tmp_path)
    assert find_skill(root, "agentonly") == agentonly.resolve()
