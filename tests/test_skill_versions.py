"""The skill page lists the same git refs Compare offers for that skill."""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from skillgate_ai.api import create_app
from skillgate_ai.cli import app

runner = CliRunner()


def _git(repo: Path, *args: str) -> None:
    subprocess.check_call(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", *args],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _skill_refs(repo: Path) -> list[str]:
    out = subprocess.check_output(
        ["git", "log", "-5", "--format=%h", "--", "skills/rh-split"],
        cwd=repo,
        text=True,
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def _rh_split_repo(tmp_path: Path) -> tuple[Path, Path, list[str]]:
    repo = tmp_path / "proj"
    skill = repo / "skills" / "rh-split"
    skill.mkdir(parents=True)
    _git(repo, "init")
    for label in ("one", "two", "three"):
        (skill / "SKILL.md").write_text(
            f"---\nname: rh-split\ndescription: Split a file into rows.\n---\n# {label}\n",
            encoding="utf-8",
        )
        _git(repo, "add", "skills/rh-split/SKILL.md")
        _git(repo, "commit", "-m", f"rh-split {label}")
    (repo / "notes.txt").write_text("unrelated\n", encoding="utf-8")
    _git(repo, "add", "notes.txt")
    _git(repo, "commit", "-m", "unrelated notes")
    refs = _skill_refs(repo)
    assert len(refs) == 3
    return repo, skill, refs


def _client(root: Path, monkeypatch) -> TestClient:
    monkeypatch.setenv("SKILLGATE_MODE", "local")
    monkeypatch.setenv("SKILLGATE_ROOT", str(root))
    monkeypatch.setenv("SKILLGATE_CURSOR_SKILLS", str(root / "cursor-skills"))
    monkeypatch.setenv("SKILLGATE_CODEX_SKILLS", str(root / "codex-skills"))
    monkeypatch.setenv("SKILLGATE_CLAUDE_SKILLS", str(root / "claude-skills"))
    return TestClient(create_app(root=root), base_url="http://127.0.0.1:8765")


def test_skill_page_lists_the_same_git_refs_as_compare(tmp_path: Path, monkeypatch) -> None:
    repo, skill, refs = _rh_split_repo(tmp_path)
    detail = _client(repo, monkeypatch).get("/api/skills/rh-split").json()
    listed = [str(row.get("semver") or "") for row in detail["versions"]]
    assert listed == refs
    assert detail["skill"]["version_count"] == 3
    assert all(row.get("created_at") for row in detail["versions"])

    monkeypatch.chdir(repo)
    history = runner.invoke(app, ["history", "--pack", str(skill)])
    history_out = history.stdout + history.stderr
    assert history.exit_code == 0, history_out
    for ref in refs:
        assert ref in history_out
    assert "unrelated notes" not in history_out

    dry = runner.invoke(app, ["compare", "versions", str(skill), "--dry-run"])
    dry_out = dry.stdout + dry.stderr
    assert dry.exit_code == 0, dry_out
    git_line = next(line for line in dry_out.splitlines() if line.startswith("Git refs:"))
    assert git_line == "Git refs: " + ", ".join(refs)


def test_skill_outside_git_has_no_versions(tmp_path: Path, monkeypatch) -> None:
    skill = tmp_path / "skills" / "rh-split"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: rh-split\ndescription: Split a file into rows.\n---\n# one\n",
        encoding="utf-8",
    )
    detail = _client(tmp_path, monkeypatch).get("/api/skills/rh-split").json()
    assert detail["versions"] == []
    assert detail["skill"]["version_count"] == 0
