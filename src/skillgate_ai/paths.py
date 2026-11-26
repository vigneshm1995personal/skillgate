"""Project-root discovery: repo (skills/ + evals/) or a single skill pack."""

from __future__ import annotations

import os
from pathlib import Path

from skillgate_ai.fs_anchor import FsAnchor


from skillgate_ai.path_traversal import PathTraversalError

__all__ = ["PathTraversalError", "FsAnchor"]


def filesystem_path_under(anchor: FsAnchor, *parts: str | Path) -> str:
    """Resolved absolute path under a fixed anchor (separator-aware containment)."""
    from skillgate_ai.fs_anchor import anchor_base
    if any(str(part) in {".", ".."} or ".." in Path(str(part)).parts for part in parts):
        raise PathTraversalError("Path escapes the allowed root.")
    pieces = [str(part) for part in parts]
    base_path = anchor_base(anchor)
    joined = os.path.join(base_path, *pieces) if pieces else base_path
    fullpath = os.path.realpath(joined)
    if fullpath == base_path or fullpath.startswith(base_path + os.sep):
        return fullpath
    raise PathTraversalError("Path escapes the allowed root.")


def contained_path(root: str | Path, *parts: str | Path) -> Path:
    """Join ``parts`` under ``root`` using fixed anchors."""
    from skillgate_ai.trusted_roots import pack_access_root

    probe = Path(root).resolve()
    piece_parts = [str(p) for p in parts]
    env = os.environ.get("SKILLGATE_ROOT")
    if env and is_under_root(probe, Path(env).resolve()):
        rel = probe.relative_to(Path(env).resolve())
        return Path(filesystem_path_under(FsAnchor.SKILLGATE_ENV, *rel.parts, *piece_parts))
    workspace = project_root().resolve()
    if is_under_root(probe, workspace):
        rel = probe.relative_to(workspace)
        return Path(filesystem_path_under(FsAnchor.WORKSPACE, *rel.parts, *piece_parts))
    anchor, prefix = pack_access_root(probe)
    return Path(filesystem_path_under(anchor, *prefix, *piece_parts))


def require_under(root: str | Path, path: str | Path) -> Path:
    """Resolve ``path`` and return it when it lies under ``root``."""
    base_path = os.path.normpath(os.path.realpath(str(root)))
    target = os.path.normpath(os.path.realpath(str(path)))
    if not (target == base_path or target.startswith(base_path + os.sep)):
        raise PathTraversalError("Path is outside the allowed root.")
    return Path(target)


def is_skill_pack(path: str | Path) -> bool:
    probe = Path(path)
    try:
        return (probe / "SKILL.md").is_file() and (probe / "evals").is_dir()
    except OSError:
        return False


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
    try:
        skills = candidate / "skills"
        return skills.is_dir()
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


def skill_pack_root(skill_path: str | Path) -> Path:
    """Resolved skill pack under workspace, agent skill root, or registered standalone mount."""
    from skillgate_ai.trusted_roots import skill_pack_root_from_access

    return skill_pack_root_from_access(skill_path)


def user_skillgate_dir() -> Path:
    """Per-user fallback folder `~/.skillgate` (read-only fallback; never written)."""
    return Path.home() / ".skillgate"


def config_root_for(path: str | Path | None = None) -> Path:
    """Folder that holds `.skillgate/keys`, walking up from a pack if given.

    Docker ``check /pack`` has no workspace `skills/` and no keys file; the pack
    itself is the config/lock root so `.skillgate/` lands on the mount.
    """
    if path is not None:
        start = Path(os.path.realpath(os.path.expanduser(str(path))))
    else:
        start = Path.cwd()
    pack = None
    nearest_workspace: Path | None = None
    nearest_keys: Path | None = None
    for candidate in (start, *start.parents):
        if nearest_workspace is None and _has_workspace_skills(candidate):
            nearest_workspace = candidate
        try:
            if nearest_keys is None and (candidate / ".skillgate" / "keys").is_file():
                nearest_keys = candidate
        except OSError:
            pass
        try:
            is_pack = is_skill_pack(candidate)
            has_skill_md = (candidate / "SKILL.md").is_file()
            has_evals = (candidate / "evals").is_dir()
            start_dir = candidate == start and candidate.is_dir()
        except OSError:
            is_pack = has_skill_md = has_evals = start_dir = False
        if pack is None and (is_pack or has_skill_md or has_evals or start_dir):
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
    return Path(pack_path_string(root, rel))


def pack_path_string(root: str | Path, rel: str) -> str:
    """Validated pack-relative path as a filesystem string."""
    anchor, prefix = pack_access_root(root)
    from skillgate_ai.contained_fs import _split_rel

    return filesystem_path_under(anchor, *prefix, *_split_rel(rel))


def _rel_under_config_root(path: str | Path) -> tuple[Path, tuple[str, ...]] | None:
    anchor = project_root().resolve()
    try:
        rel = Path(path).expanduser().resolve().relative_to(anchor)
    except ValueError:
        return None
    return anchor, rel.parts


def pack_access_root(skill_path: str | Path) -> tuple[FsAnchor, tuple[str, ...]]:
    """Workspace or agent anchor and relative path segments to a skill pack root."""
    from skillgate_ai.trusted_roots import pack_access_root as trusted_pack_access_root

    return trusted_pack_access_root(skill_path)


def is_under_root(path: str | Path, root: str | Path) -> bool:
    try:
        base_path = os.path.normpath(os.path.realpath(str(root)))
        target = os.path.normpath(os.path.realpath(str(path)))
        return target == base_path or target.startswith(base_path + os.sep)
    except (ValueError, OSError):
        return False
