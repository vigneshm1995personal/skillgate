"""Characterization tests for pack mount / workspace classification (CodeQL-safe refactors)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from skillgate_ai.fs_anchor import FsAnchor
from skillgate_ai.paths import PathTraversalError, config_root_for, contained_path
from skillgate_ai.trusted_roots import (
    pack_access_root,
    register_standalone_pack_for_cli,
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
    assert anchor is FsAnchor.WORKSPACE
    assert parts == ("skill",)


def test_empty_work_dir_pins_for_contained_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
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
    pack = tmp_path / "standalone"
    pack.mkdir()
    (pack / "SKILL.md").write_text("---\nname: solo\n---\n", encoding="utf-8")
    (pack / "evals").mkdir()
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    register_standalone_pack_for_cli(pack)
    anchor, parts = pack_access_root(pack)
    assert anchor is FsAnchor.SKILLGATE_ENV
    assert parts == ()
