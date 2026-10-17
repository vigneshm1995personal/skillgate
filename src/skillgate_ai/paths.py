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
        # Workspace layout: `skillgate check pdf` → `skills/pdf` when present.
        if len(path.parts) == 1 and not path.is_absolute():
            skill_pack = Path(root) / "skills" / path
            if (skill_pack / "SKILL.md").is_file():
                return skill_pack.resolve()
    return cwd_hit.resolve()


def _has_workspace_skills(candidate: Path) -> bool:
    """A workspace is any folder with ``skills/`` (including right after ``skillgate init``)."""
    return (candidate / "skills").is_dir()


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
    nearest_workspace: Path | None = None
    nearest_keys: Path | None = None
    for candidate in (start, *start.parents):
        if nearest_workspace is None and _has_workspace_skills(candidate):
            nearest_workspace = candidate
        if nearest_keys is None and (candidate / ".skillgate" / "keys").is_file():
            nearest_keys = candidate
        if pack is None and (is_skill_pack(candidate) or (candidate / "SKILL.md").is_file()):
            pack = candidate
    if nearest_workspace is not None:
        return nearest_workspace
    if nearest_keys is not None:
        return nearest_keys
    if pack is not None:
        return pack
    return project_root()


def is_under_root(path: str | Path, root: str | Path) -> bool:
    try:
        Path(path).expanduser().resolve().relative_to(Path(root).expanduser().resolve())
        return True
    except (ValueError, OSError):
        return False
