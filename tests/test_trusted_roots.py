from __future__ import annotations

import os
from pathlib import Path

import pytest

from skillgate_ai.paths import PathTraversalError, project_root
from skillgate_ai.trusted_roots import (
    pack_access_root,
    register_standalone_pack_for_cli,
    skill_pack_root_from_access,
)


def test_pack_access_under_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "proj"
    skills = ws / "skills" / "pdf"
    skills.mkdir(parents=True)
    monkeypatch.chdir(ws)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    (skills / "SKILL.md").write_text("---\nname: pdf\n---\n", encoding="utf-8")
    (skills / "evals").mkdir()
    anchor, parts = pack_access_root(skills)
    assert anchor == project_root().resolve()
    assert parts[-2:] == ("skills", "pdf")


def test_standalone_pack_registers_skillgate_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pack = tmp_path / "standalone"
    pack.mkdir()
    (pack / "SKILL.md").write_text("---\nname: solo\n---\n", encoding="utf-8")
    (pack / "evals").mkdir()
    cwd = tmp_path / "other"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    register_standalone_pack_for_cli(pack)
    assert os.environ.get("SKILLGATE_ROOT") == str(pack.resolve())
    anchor, parts = pack_access_root(pack)
    assert anchor == pack.resolve()
    assert parts == ()


def test_rejects_outside_all_roots() -> None:
    with pytest.raises(PathTraversalError):
        pack_access_root("/etc/passwd")


def test_sibling_prefix_under_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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