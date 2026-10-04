"""Project-root discovery: repo (skills/ + evals/) or a single skill pack."""

from __future__ import annotations

import os
from pathlib import Path


def is_skill_pack(path: str | Path) -> bool:
    root = Path(path)
    return (root / "SKILL.md").is_file() and (root / "evals").is_dir()


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
