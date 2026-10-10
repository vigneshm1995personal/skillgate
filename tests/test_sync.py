from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path

import pytest

from skillgate_ai.sync import install_launchd_plist, sync_once


def _init_repo(path: Path, skills: list[str]) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=path, check=True, capture_output=True)
    for name in skills:
        folder = path / "skills" / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "SKILL.md").write_text(
            "---\n"
            f"name: {name}\n"
            "description: A skill for sync tests. Use when verifying install.\n"
            "---\n\n"
            f"# {name}\n",
            encoding="utf-8",
        )
    subprocess.run(["git", "add", "-A"], cwd=path, check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.email=t@example.com",
            "-c",
            "user.name=Test",
            "commit",
            "-m",
            "seed",
        ],
        cwd=path,
        check=True,
        capture_output=True,
    )
    return path


def test_sync_copies_skills_into_targets(
    project_root: Path, tmp_path: Path
) -> None:
    repo = _init_repo(tmp_path / "repo", ["notes", "pdf-tools"])
    result = sync_once(str(repo), targets=["cursor", "codex", "claude"])
    assert set(result["skills"]) == {"notes", "pdf-tools"}
    for target in ("cursor", "codex", "claude"):
        root = Path(os.environ[f"SKILLGATE_{target.upper()}_SKILLS"])
        assert (root / "notes" / "SKILL.md").is_file()
        assert (root / "pdf-tools" / "SKILL.md").is_file()


def test_sync_never_deletes_unmanaged(project_root: Path, tmp_path: Path) -> None:
    cursor_root = Path(os.environ["SKILLGATE_CURSOR_SKILLS"])
    cursor_root.mkdir(parents=True, exist_ok=True)
    # Unrelated folder must survive every sync.
    (cursor_root / "other" / "SKILL.md").parent.mkdir(parents=True, exist_ok=True)
    (cursor_root / "other" / "SKILL.md").write_text("---\nname: other\ndescription: keep\n---\n\n# other\n")

    repo_one = _init_repo(tmp_path / "repo-one", ["keep", "drop"])
    sync_once(str(repo_one), targets=["cursor"])
    assert (cursor_root / "keep" / "SKILL.md").is_file()
    assert (cursor_root / "drop" / "SKILL.md").is_file()

    repo_two = _init_repo(tmp_path / "repo-two", ["keep"])
    sync_once(str(repo_two), targets=["cursor"])
    # Managed-then-removed skill is deleted; unrelated folder survives.
    assert (cursor_root / "keep" / "SKILL.md").is_file()
    assert not (cursor_root / "drop").exists()
    assert (cursor_root / "other" / "SKILL.md").is_file()


def test_sync_rejects_nested_symlink(tmp_path: Path) -> None:
    from skillgate_ai.errors import SkillGateError
    from skillgate_ai.sync import _reject_symlinks

    skill = tmp_path / "evil"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: evil\ndescription: sync skill with symlink\n---\n", encoding="utf-8"
    )
    target = tmp_path / "outside"
    target.mkdir()
    try:
        os.symlink(target, skill / "link")
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")
    with pytest.raises(SkillGateError):
        _reject_symlinks(skill)


def test_sync_rejects_top_level_symlink(tmp_path: Path) -> None:
    from skillgate_ai.errors import SkillGateError
    from skillgate_ai.sync import _reject_symlinks

    target = tmp_path / "real"
    target.mkdir()
    (target / "SKILL.md").write_text(
        "---\nname: real\ndescription: real skill\n---\n", encoding="utf-8"
    )
    link = tmp_path / "evil"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not supported here")
    with pytest.raises(SkillGateError):
        _reject_symlinks(link)


def test_sync_install_launchd_plist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from skillgate_ai import sync as sync_mod

    launch_dir = tmp_path / "LaunchAgents"
    monkeypatch.setattr(sync_mod, "launch_agents_dir", lambda: launch_dir)
    dest = install_launchd_plist(
        "https://github.com/acme/skills.git", targets=["cursor"], interval=60
    )
    assert dest.is_file()
    plist = plistlib.loads(dest.read_bytes())
    assert plist["RunAtLoad"] is True
    assert "https://github.com/acme/skills.git" in plist["ProgramArguments"]
    assert os.stat(dest).st_mode & 0o777 == 0o644