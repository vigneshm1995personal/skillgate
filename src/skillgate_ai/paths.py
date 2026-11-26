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
    from skillgate_ai.pack_layout import relative_segments_under
    from skillgate_ai.trusted_roots import normalize_pack_target, pack_access_root

    piece_parts = [str(p) for p in parts]
    for part in piece_parts:
        if part in {".", ".."} or ".." in Path(part).parts:
            raise PathTraversalError("Path escapes the allowed root.")
    probe = os.path.realpath(os.fsdecode(normalize_pack_target(root)))
    env = os.environ.get("SKILLGATE_ROOT")
    if env and ".." not in Path(env).parts:
        gate = os.path.realpath(env)
        rel = relative_segments_under(gate, probe)
        if rel is not None:
            return Path(filesystem_path_under(FsAnchor.SKILLGATE_ENV, *rel, *piece_parts))
    workspace = os.path.realpath(os.fsdecode(project_root()))
    rel = relative_segments_under(workspace, probe)
    if rel is not None:
        return Path(filesystem_path_under(FsAnchor.WORKSPACE, *rel, *piece_parts))
    anchor, prefix = pack_access_root(root)
    return Path(filesystem_path_under(anchor, *prefix, *piece_parts))


def require_under(root: str | Path, path: str | Path) -> Path:
    """Resolve ``path`` and return it when it lies under ``root``."""
    base_path = os.path.normpath(os.path.realpath(str(root)))
    target = os.path.normpath(os.path.realpath(str(path)))
    if not (target == base_path or target.startswith(base_path + os.sep)):
        raise PathTraversalError("Path is outside the allowed root.")
    return Path(target)


def is_skill_pack(path: str | Path) -> bool:
    from skillgate_ai.pack_layout import (
        discovery_skill_pack_dir,
        loose_pack_mount_at,
        relative_segments_under,
        strict_skill_pack_at,
    )
    from skillgate_ai.trusted_roots import _agent_roots, normalize_pack_target, pack_access_root

    try:
        resolved = normalize_pack_target(path)
    except PathTraversalError:
        return False
    try:
        anchor, parts = pack_access_root(resolved)
        if loose_pack_mount_at(anchor, *parts):
            return True
    except PathTraversalError:
        pass
    if discovery_skill_pack_dir(resolved):
        return True
    target = os.path.realpath(os.fsdecode(resolved))
    env = os.environ.get("SKILLGATE_ROOT")
    if env and ".." not in Path(env).parts:
        gate = os.path.realpath(env)
        gate_parts = relative_segments_under(gate, target)
        if gate_parts is not None:
            return strict_skill_pack_at(FsAnchor.SKILLGATE_ENV, *gate_parts)
    workspace = _workspace_realpath_for_pack_check()
    workspace_parts = relative_segments_under(workspace, target)
    if workspace_parts is not None:
        return strict_skill_pack_at(FsAnchor.WORKSPACE, *workspace_parts)
    for getter, agent_anchor in _agent_roots():
        try:
            agent = os.path.realpath(os.fsdecode(getter().resolve()))
        except OSError:
            continue
        agent_parts = relative_segments_under(agent, target)
        if agent_parts is not None and len(agent_parts) == 1:
            return strict_skill_pack_at(agent_anchor, *agent_parts)
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


def _workspace_realpath_for_pack_check() -> str:
    env = os.environ.get("SKILLGATE_ROOT")
    if env and ".." not in Path(env).parts:
        return os.path.realpath(env)
    cwd = Path.cwd()
    for candidate in (cwd, *cwd.parents):
        if _has_workspace_skills(candidate):
            return os.path.realpath(os.fsdecode(candidate))
        from skillgate_ai.pack_layout import discovery_skill_pack_dir

        if discovery_skill_pack_dir(candidate):
            return os.path.realpath(os.fsdecode(candidate))
    return os.path.realpath(os.fsdecode(cwd))


def _has_workspace_skills(candidate: Path) -> bool:
    """A workspace is any folder with ``skills/`` (including right after ``skillgate init``)."""
    from skillgate_ai.pack_layout import discovery_has_skills_dir

    return discovery_has_skills_dir(candidate)


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
        if pack is None:
            from skillgate_ai.pack_layout import discovery_skill_pack_dir

            if discovery_skill_pack_dir(candidate):
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
            from skillgate_ai.pack_layout import discovery_keys_file, discovery_pack_markers

            if nearest_keys is None and discovery_keys_file(candidate):
                nearest_keys = candidate
        except OSError:
            pass
        try:
            from skillgate_ai.pack_layout import discovery_is_directory

            has_skill_md, has_evals, is_pack = discovery_pack_markers(candidate)
            start_dir = candidate == start and discovery_is_directory(candidate)
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
