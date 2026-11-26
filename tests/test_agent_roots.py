from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from skillgate_ai import agent_roots, deploy
from skillgate_ai.agent_roots import (
    claude_skills_root,
    codex_skills_root,
    cursor_skills_root,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("env_var", "fn"),
    [
        ("SKILLGATE_CURSOR_SKILLS", cursor_skills_root),
        ("SKILLGATE_CODEX_SKILLS", codex_skills_root),
        ("SKILLGATE_CLAUDE_SKILLS", claude_skills_root),
    ],
)
def test_agent_root_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_var: str, fn: object
) -> None:
    target = (tmp_path / "skills-dir").resolve()
    target.mkdir()
    monkeypatch.setenv(env_var, str(target))
    assert fn() == target  # type: ignore[operator]


def test_agent_roots_default_under_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "SKILLGATE_CURSOR_SKILLS",
        "SKILLGATE_CODEX_SKILLS",
        "SKILLGATE_CLAUDE_SKILLS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert cursor_skills_root() == (tmp_path / ".cursor" / "skills").resolve()
    assert codex_skills_root() == (tmp_path / ".codex" / "skills").resolve()
    assert claude_skills_root() == (tmp_path / ".claude" / "skills").resolve()


def test_deploy_reexports_agent_roots() -> None:
    assert deploy.cursor_skills_root is agent_roots.cursor_skills_root
    assert deploy.codex_skills_root is agent_roots.codex_skills_root
    assert deploy.claude_skills_root is agent_roots.claude_skills_root


def test_fs_core_import_does_not_load_deploy(tmp_path: Path) -> None:
    script = """
import os
import sys
os.environ["HOME"] = sys.argv[1]
os.environ["SKILLGATE_CURSOR_SKILLS"] = sys.argv[2]
from skillgate_ai.fs_anchor import FsAnchor, anchor_base
from skillgate_ai import trusted_roots, pack_io

anchor_base(FsAnchor.AGENT_CURSOR)
trusted_roots._agent_roots()
if "skillgate_ai.deploy" in sys.modules:
    raise SystemExit(1)
"""
    skills = tmp_path / "cursor-skills"
    skills.mkdir()
    proc = subprocess.run(
        [sys.executable, "-I", "-c", script, str(tmp_path), str(skills)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
