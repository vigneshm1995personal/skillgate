"""Pack layout probes via fixed anchors only (no user path as Path join base)."""

from __future__ import annotations

import os
from pathlib import Path

from skillgate_ai.contained_fs import isdir_at, isfile_at
from skillgate_ai.fs_anchor import FsAnchor


def relative_segments_under(base_real: str, target_real: str) -> tuple[str, ...] | None:
    """Validated path segments from ``base_real`` to ``target_real``, or ``None`` if outside."""
    base = os.path.normpath(base_real)
    target = os.path.normpath(target_real)
    if not (target == base or target.startswith(base + os.sep)):
        return None
    tail = target[len(base) :].lstrip(os.sep)
    if not tail:
        return ()
    parts = tuple(piece for piece in tail.split(os.sep))
    if any(piece in {".", ".."} for piece in parts):
        return None
    return parts


def strict_skill_pack_at(anchor: FsAnchor, *rel_parts: str) -> bool:
    return isfile_at(anchor, *rel_parts, "SKILL.md") and isdir_at(anchor, *rel_parts, "evals")


def loose_pack_mount_at(anchor: FsAnchor, *rel_parts: str) -> bool:
    if strict_skill_pack_at(anchor, *rel_parts):
        return True
    if isfile_at(anchor, *rel_parts, "evals", "cases.yaml"):
        return True
    if isdir_at(anchor, *rel_parts, "scripts"):
        return True
    return isfile_at(anchor, *rel_parts, "SKILL.md")


def workspace_has_skills_dir(candidate_real: str, workspace_real: str) -> bool:
    rel = relative_segments_under(workspace_real, candidate_real)
    if rel is None:
        rel_parts: tuple[str, ...] = ()
    else:
        rel_parts = rel
    return isdir_at(FsAnchor.WORKSPACE, *rel_parts, "skills")


def single_path_segment_name(name: str) -> bool:
    if not name or name in {".", ".."}:
        return False
    return ".." not in Path(name).parts and os.sep not in name and "/" not in name


def discovery_skill_pack_dir(candidate: Path) -> bool:
    """Cwd-walk helper only (literal subpaths; not for user-supplied CLI paths)."""
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        if ".." in Path(cand).parts:
            return False
        skill = os.path.join(cand, "SKILL.md")
        evals = os.path.join(cand, "evals")
        return os.path.isfile(skill) and os.path.isdir(evals)
    except (OSError, ValueError):
        return False
