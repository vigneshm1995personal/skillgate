"""Project-root discovery: repo (skills/ + evals/) or a single skill pack."""

from __future__ import annotations

import os
from pathlib import Path


class PathTraversalError(ValueError):
    """Resolved path escapes the allowed root."""


def contained_path(root: str | Path, *parts: str | Path) -> Path:
    """Join ``parts`` under ``root`` and return the resolved path when it stays inside ``root``."""
    base = os.path.realpath(os.path.expanduser(str(root)))
    if any(str(part) in {".", ".."} or ".." in Path(str(part)).parts for part in parts):
        raise PathTraversalError("Path escapes the allowed root.")
    pieces = [str(part) for part in parts]
    joined = os.path.join(base, *pieces) if pieces else base
    target = os.path.realpath(os.path.expanduser(joined))
    try:
        common = os.path.commonpath([base, target])
    except ValueError as exc:
        raise PathTraversalError("Path escapes the allowed root.") from exc
    if common != base:
        raise PathTraversalError("Path escapes the allowed root.")
    return Path(target)


def require_under(root: str | Path, path: str | Path) -> Path:
    """Resolve ``path`` and return it when it lies under ``root``."""
    base = os.path.realpath(os.path.expanduser(str(root)))
    target = os.path.realpath(os.path.expanduser(str(path)))
    try:
        common = os.path.commonpath([base, target])
    except ValueError as exc:
        raise PathTraversalError("Path is outside the allowed root.") from exc
    if common != base:
        raise PathTraversalError("Path is outside the allowed root.")
    return Path(target)


def is_skill_pack(path: str | Path) -> bool:
    base = os.path.realpath(os.path.expanduser(str(path)))
    return os.path.isfile(os.path.join(base, "SKILL.md")) and os.path.isdir(
        os.path.join(base, "evals")
    )


def nearest_skill_pack(start: str | Path | None = None) -> Path | None:
    """First folder from start (default cwd) upward that is a skill pack."""
    origin = Path(start).expanduser().resolve() if start is not None else Path.cwd().resolve()
    for candidate in (origin, *origin.parents):
        if is_skill_pack(candidate):
            return candidate
    return None


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
        rooted = contained_path(root, path)
        if rooted.exists():
            return rooted
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


def skill_pack_root(skill_path: str | Path) -> Path:
    """Resolved skill pack folder under its config root, or a direct agent-skill install."""
    text = os.path.expanduser(str(skill_path))
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    resolved = Path(os.path.realpath(text))
    bound = Path(os.path.realpath(str(config_root_for(resolved))))
    try:
        return require_under(bound, resolved)
    except PathTraversalError:
        from skillgate_ai.catalog import _immediate_agent_skill

        if _immediate_agent_skill(resolved):
            return resolved
        base = str(resolved)
        if (
            is_skill_pack(resolved)
            or os.path.isfile(os.path.join(base, "SKILL.md"))
            or os.path.isfile(os.path.join(base, "evals", "cases.yaml"))
            or os.path.isdir(os.path.join(base, "evals"))
            or os.path.isdir(base)
        ):
            return resolved
        raise


def user_skillgate_dir() -> Path:
    """Per-user fallback folder `~/.skillgate` (read-only fallback; never written)."""
    return Path.home() / ".skillgate"


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


def pack_file_at(root: str | Path, rel: str) -> Path:
    """Pack-relative file path under ``root`` (e.g. ``evals/cases.yaml``)."""
    cleaned = rel.replace("\\", "/").strip().lstrip("/")
    parts = [piece for piece in cleaned.split("/") if piece and piece not in {".", ""}]
    if not parts or any(piece == ".." for piece in parts):
        raise PathTraversalError("Path escapes the allowed root.")
    return contained_path(root, *parts)


def is_under_root(path: str | Path, root: str | Path) -> bool:
    try:
        base = os.path.realpath(os.path.expanduser(str(root)))
        target = os.path.realpath(os.path.expanduser(str(path)))
        return os.path.commonpath([base, target]) == base
    except (ValueError, OSError):
        return False


