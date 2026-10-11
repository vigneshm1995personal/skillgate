"""Project-root discovery: repo (skills/ + evals/) or a single skill pack."""

from __future__ import annotations

import os
from pathlib import Path


def is_skill_pack(path: str | Path) -> bool:
    root = Path(path)
    return (root / "SKILL.md").is_file() and (root / "evals").is_dir()


def resolve_user_path(target: str | Path, root: Path | None = None) -> Path:
    """Resolve a CLI path against the current folder first, then the project root.

    `skillgate check ./pdf` from a subfolder of a project must use cwd/pdf, not
    <project>/pdf. Absolute paths are unchanged.
    """
    path = Path(target).expanduser()
    if path.is_absolute():
        return path.resolve()
    cwd_hit = Path.cwd() / path
    if cwd_hit.exists():
        return cwd_hit.resolve()
    if root is not None:
        rooted = Path(root) / path
        if rooted.exists():
            return rooted.resolve()
    return cwd_hit.resolve()


def project_root() -> Path:
    env = os.environ.get("SKILLGATE_ROOT")
    if env:
        return Path(env).resolve()
    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        skills = candidate / "skills"
        if skills.is_dir() and any(
            child.is_dir() and (child / "SKILL.md").is_file() for child in skills.iterdir()
        ):
            return candidate
        if is_skill_pack(candidate):
            return candidate
    return cwd
