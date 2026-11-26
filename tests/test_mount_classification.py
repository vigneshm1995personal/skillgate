"""Characterization tests for pack mount / workspace classification (CodeQL-safe refactors)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from skillgate_ai.allow_root import set_cli_allow_root
from skillgate_ai.fs_anchor import FsAnchor
from skillgate_ai.paths import PathTraversalError, config_root_for, contained_path
from skillgate_ai.trusted_roots import (
    pack_access_root,
    skill_pack_root_from_access,
)


def _symlink_or_skip(src: Path, dest: Path) -> None:
    try:
        os.symlink(src, dest)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")


def test_symlinked_skill_pack_access_matches_real_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = tmp_path / "project"
    real = workspace / "shared" / "pdf-tools"
    real.mkdir(parents=True)
    (real / "SKILL.md").write_text("---\nname: pdf-tools\n---\n", encoding="utf-8")
    (real / "evals").mkdir()
    (workspace / "skills").mkdir(parents=True)
    link = workspace / "skills" / "pdf-tools"
    _symlink_or_skip(real, link)
    monkeypatch.chdir(workspace)
    monkeypatch.setenv("SKILLGATE_ROOT", str(workspace))
    anchor_link, parts_link = pack_access_root(link)
    anchor_real, parts_real = pack_access_root(real)
    assert anchor_link is anchor_real
    assert parts_link == parts_real
    skill_pack_root_from_access(link)


def test_history_style_pack_without_skill_md_mounts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = tmp_path / "skill"
    (pack / "evals" / "history").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    anchor, parts = pack_access_root(pack)
    assert anchor in {FsAnchor.WORKSPACE, FsAnchor.SKILLGATE_ENV}
    assert parts == ("skill",)


def test_empty_work_dir_pins_for_contained_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "proj"
    (ws / "skills").mkdir(parents=True)
    work = ws / "work"
    work.mkdir()
    monkeypatch.chdir(ws)
    monkeypatch.setenv("SKILLGATE_ROOT", str(ws))
    dest = contained_path(work, "demo")
    assert dest == (work / "demo").resolve()


def test_config_root_for_walk_under_skillgate_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "proj"
    (ws / "skills").mkdir(parents=True)
    skill = ws / "skills" / "pdf"
    skill.mkdir()
    (skill / "SKILL.md").write_text("x", encoding="utf-8")
    (skill / "evals").mkdir()
    monkeypatch.setenv("SKILLGATE_ROOT", str(ws))
    root = config_root_for(skill)
    assert root.resolve() == ws.resolve()


def test_prefix_sibling_outside_skillgate_env_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Same contract as test_sibling_prefix_under_workspace: sibling mount is rejected."""
    root = tmp_path / "a"
    root.mkdir()
    (root / "skills").mkdir()
    sibling = tmp_path / "ab"
    sibling.mkdir()
    (sibling / "SKILL.md").write_text("x", encoding="utf-8")
    (sibling / "evals").mkdir()
    monkeypatch.chdir(root)
    monkeypatch.setenv("SKILLGATE_ROOT", str(root))
    with pytest.raises(PathTraversalError):
        skill_pack_root_from_access(sibling)


def test_standalone_classification_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ws = tmp_path / "proj"
    (ws / "skills").mkdir(parents=True)
    parent = tmp_path / "out"
    pack = parent / "standalone"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text("---\nname: solo\n---\n", encoding="utf-8")
    (pack / "evals").mkdir()
    monkeypatch.chdir(ws)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    set_cli_allow_root(parent)
    anchor, parts = pack_access_root(pack)
    assert anchor is FsAnchor.ALLOW_ROOT
    assert parts == ("standalone",)


def test_layout_classifiers_on_workspace_root(tmp_path: Path) -> None:
    from skillgate_ai.pack_layout import (
        layout_has_skills_dir,
        layout_is_directory,
        layout_pack_markers,
        layout_skill_pack_at_root,
    )

    root = tmp_path / "ws"
    (root / "skills").mkdir(parents=True)
    resolved = os.path.realpath(root)
    assert layout_has_skills_dir(resolved)
    assert layout_is_directory(resolved)
    assert layout_pack_markers(resolved) == (False, False, False)
    assert layout_skill_pack_at_root(resolved) is False
    pack = root / "skills" / "solo"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text("---\nname: solo\n---\n", encoding="utf-8")
    (pack / "evals").mkdir()
    pack_real = os.path.realpath(pack)
    assert layout_skill_pack_at_root(pack_real)
    assert layout_pack_markers(pack_real)[2]


def test_layout_keys_file_and_rejects_relative_root(tmp_path: Path) -> None:
    from skillgate_ai.pack_layout import layout_keys_file

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / ".skillgate").mkdir()
    (ws / ".skillgate" / "keys").write_text("{}", encoding="utf-8")
    assert layout_keys_file(os.path.realpath(ws)) is True
    assert layout_keys_file("relative/path") is False


def test_discovery_helpers_classify_workspace(tmp_path: Path) -> None:
    from skillgate_ai.pack_layout import (
        discovery_has_skills_dir,
        discovery_is_directory,
        discovery_keys_file,
        discovery_pack_markers,
        discovery_skill_pack_dir,
    )

    ws = tmp_path / "ws"
    (ws / "skills").mkdir(parents=True)
    pack = ws / "skills" / "solo"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text("---\nname: solo\n---\n", encoding="utf-8")
    (pack / "evals").mkdir()
    (ws / ".skillgate").mkdir(parents=True)
    (ws / ".skillgate" / "keys").write_text("{}", encoding="utf-8")
    assert discovery_is_directory(ws)
    assert discovery_has_skills_dir(ws)
    assert discovery_keys_file(ws)
    assert discovery_skill_pack_dir(pack)
    skill, evals, as_pack = discovery_pack_markers(pack)
    assert skill and evals and as_pack
    assert discovery_skill_pack_dir(tmp_path / "missing") is False


def test_relative_segments_under_rejects_traversal() -> None:
    from skillgate_ai.pack_layout import relative_segments_under

    base = os.path.realpath("/tmp/ws")
    assert relative_segments_under(base, os.path.join(base, "skills", "pdf")) == ("skills", "pdf")
    assert relative_segments_under(base, base) == ()
    assert relative_segments_under(base, os.path.join(base, "..", "etc")) is None
