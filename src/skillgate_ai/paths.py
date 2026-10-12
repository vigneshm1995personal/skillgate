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


def _has_workspace_skills(candidate: Path) -> bool:
    skills = candidate / "skills"
    if not skills.is_dir():
        return False
    try:
        return any(child.is_dir() and (child / "SKILL.md").is_file() for child in skills.iterdir())
    except OSError:
        return False


def project_root() -> Path:
    env = os.environ.get("SKILLGATE_ROOT")
    if env:
        return Path(env).resolve()
    cwd = Path.cwd()
    workspace = None
    pack = None
    for candidate in (cwd, *cwd.parents):
        if _has_workspace_skills(candidate):
            workspace = candidate
            break
        if pack is None and is_skill_pack(candidate):
            pack = candidate
    if workspace is not None:
        return workspace
    if pack is not None:
        return pack
    return cwd


def config_root_for(path: str | Path | None = None) -> Path:
    """Folder that holds `.skillgate/keys`, walking up from a pack if given.

    Docker ``check /pack`` has no workspace `skills/` and no keys file; the pack
    itself is the config/lock root so `.skillgate/` lands on the mount.
    """
    start = Path(path).expanduser().resolve() if path is not None else Path.cwd()
    pack = None
    for candidate in (start, *start.parents):
        if (candidate / ".skillgate" / "keys").is_file():
            return candidate
        if _has_workspace_skills(candidate):
            return candidate
        if pack is None and (is_skill_pack(candidate) or (candidate / "SKILL.md").is_file()):
            pack = candidate
    if pack is not None:
        return pack
    return project_root()


def is_under_root(path: str | Path, root: str | Path) -> bool:
    try:
        Path(path).expanduser().resolve().relative_to(Path(root).expanduser().resolve())
        return True
    except (ValueError, OSError):
        return False
