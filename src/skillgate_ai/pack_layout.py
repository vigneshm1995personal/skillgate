"""Pack layout probes: fixed suffix checks and anchor-relative probes only."""

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


def _join_root(root_real: str, *parts: str) -> str:
    if ".." in Path(root_real).parts:
        raise ValueError("invalid root")
    for part in parts:
        if part in {".", ".."} or ".." in Path(part).parts:
            raise ValueError("invalid part")
    return os.path.normpath(os.path.join(root_real, *parts))


def layout_has_skills_dir(root_real: str) -> bool:
    try:
        return os.path.isdir(_join_root(root_real, "skills"))
    except (OSError, ValueError):
        return False


def layout_skill_pack_at_root(root_real: str) -> bool:
    try:
        skill = os.path.isfile(_join_root(root_real, "SKILL.md"))
        evals = os.path.isdir(_join_root(root_real, "evals"))
        return skill and evals
    except (OSError, ValueError):
        return False


def layout_keys_file(root_real: str) -> bool:
    try:
        return os.path.isfile(_join_root(root_real, ".skillgate", "keys"))
    except (OSError, ValueError):
        return False


def layout_is_directory(root_real: str) -> bool:
    try:
        return os.path.isdir(root_real)
    except OSError:
        return False


def layout_pack_markers(root_real: str) -> tuple[bool, bool, bool]:
    try:
        skill = os.path.isfile(_join_root(root_real, "SKILL.md"))
        evals = os.path.isdir(_join_root(root_real, "evals"))
        pack = layout_skill_pack_at_root(root_real)
        return skill, evals, pack
    except OSError:
        return False, False, False


def discovery_skill_pack_dir(candidate: Path) -> bool:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        if ".." in Path(cand).parts:
            return False
        return layout_skill_pack_at_root(cand)
    except (OSError, ValueError):
        return False


def discovery_has_skills_dir(candidate: Path) -> bool:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        return layout_has_skills_dir(cand)
    except OSError:
        return False


def discovery_keys_file(candidate: Path) -> bool:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        return layout_keys_file(cand)
    except OSError:
        return False


def discovery_is_directory(candidate: Path) -> bool:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        return layout_is_directory(cand)
    except OSError:
        return False


def discovery_pack_markers(candidate: Path) -> tuple[bool, bool, bool]:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        return layout_pack_markers(cand)
    except OSError:
        return False, False, False
