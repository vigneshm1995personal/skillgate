from __future__ import annotations

import os
from pathlib import Path

import pytest

from skillgate_ai.allow_root import (
    allow_root_realpaths,
    read_user_allow_root_file,
    set_cli_allow_root,
)
from skillgate_ai.fs_anchor import FsAnchor
from skillgate_ai.paths import PathTraversalError
from skillgate_ai.trusted_roots import (
    pack_access_root,
    skill_pack_root_from_access,
)


@pytest.fixture(autouse=True)
def _clear_allow_root() -> None:
    set_cli_allow_root(None)
    yield
    set_cli_allow_root(None)


def test_pack_access_under_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "proj"
    skills = ws / "skills" / "pdf"
    skills.mkdir(parents=True)
    monkeypatch.chdir(ws)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    (skills / "SKILL.md").write_text("---\nname: pdf\n---\n", encoding="utf-8")
    (skills / "evals").mkdir()
    anchor, parts = pack_access_root(skills)
    assert anchor is FsAnchor.WORKSPACE
    assert parts[-2:] == ("skills", "pdf")


def test_agent_skill_immediate_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "proj"
    (ws / "skills").mkdir(parents=True)
    agent_root = tmp_path / "cursor-skills"
    pack = agent_root / "foo"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text("---\nname: foo\n---\n", encoding="utf-8")
    (pack / "evals").mkdir()
    monkeypatch.chdir(ws)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)

    def _cursor() -> Path:
        return agent_root

    monkeypatch.setattr("skillgate_ai.deploy.cursor_skills_root", _cursor)
    anchor, parts = pack_access_root(pack)
    assert anchor is FsAnchor.AGENT_CURSOR
    assert parts == ("foo",)


def test_agent_skill_without_evals_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent_root = tmp_path / "cursor-skills"
    pack = agent_root / "foo"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text("---\nname: foo\n---\n", encoding="utf-8")
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)

    def _cursor() -> Path:
        return agent_root

    monkeypatch.setattr("skillgate_ai.deploy.cursor_skills_root", _cursor)
    anchor, parts = pack_access_root(pack)
    assert anchor is FsAnchor.AGENT_CURSOR
    assert parts == ("foo",)


def test_rejects_nested_agent_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "proj"
    (ws / "skills").mkdir(parents=True)
    agent_root = tmp_path / "cursor-skills"
    nested = agent_root / "foo" / "bar"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text("x", encoding="utf-8")
    (nested / "evals").mkdir()
    monkeypatch.chdir(ws)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)

    def _cursor() -> Path:
        return agent_root

    monkeypatch.setattr("skillgate_ai.deploy.cursor_skills_root", _cursor)
    with pytest.raises(PathTraversalError):
        pack_access_root(nested)


def test_read_user_allow_root_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    allowed = tmp_path / "packs"
    allowed.mkdir()
    cfg = tmp_path / ".skillgate" / "allow-root"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(f"{allowed}\n", encoding="utf-8")
    resolved = os.path.realpath(allowed)
    assert read_user_allow_root_file() == resolved
    assert resolved in allow_root_realpaths()


def test_rejects_etc_without_allow_root() -> None:
    with pytest.raises(PathTraversalError, match="allow-root"):
        pack_access_root("/etc")


def test_allow_root_cli_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_pack_cannot_opt_in_via_repo_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ws = tmp_path / "proj"
    (ws / "skills").mkdir(parents=True)
    pack = tmp_path / "outside" / "pack"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text("---\nname: solo\n---\n", encoding="utf-8")
    (pack / "evals").mkdir()
    (pack / "evals" / "cases.yaml").write_text(
        "schema_version: 1\nskill: solo\ncases: []\n",
        encoding="utf-8",
    )
    (pack / ".skillgate").mkdir()
    (pack / ".skillgate" / "allow-root").write_text(f"{pack}\n", encoding="utf-8")
    (pack / ".env").write_text(f"SKILLGATE_ROOT={pack}\n", encoding="utf-8")
    cwd = ws / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    from skillgate_ai.config import load_env
    from skillgate_ai.paths import config_root_for

    load_env(config_root_for(pack))
    assert __import__("os").environ.get("SKILLGATE_ROOT") is None
    with pytest.raises(PathTraversalError):
        pack_access_root(pack)


def test_pack_dotenv_skillgate_root_does_not_unlock_run_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import os

    from skillgate_ai.config import load_env
    from skillgate_ai.gate import run_check
    from skillgate_ai.paths import config_root_for

    ws = tmp_path / "proj"
    (ws / "skills").mkdir(parents=True)
    pack = tmp_path / "outside" / "solo"
    pack.mkdir(parents=True)
    (pack / "SKILL.md").write_text(
        "---\nname: solo\ndescription: Solo.\n---\n# Solo\n",
        encoding="utf-8",
    )
    (pack / "evals").mkdir()
    (pack / "evals" / "cases.yaml").write_text(
        "schema_version: 1\nskill: solo\ncases: []\n",
        encoding="utf-8",
    )
    (pack / ".env").write_text(f"SKILLGATE_ROOT={pack}\n", encoding="utf-8")
    monkeypatch.chdir(ws)
    monkeypatch.delenv("SKILLGATE_ROOT", raising=False)
    load_env(config_root_for(pack))
    assert os.environ.get("SKILLGATE_ROOT") is None
    with pytest.raises(PathTraversalError):
        run_check(str(pack), source="test", no_judge=True, live=False)


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
