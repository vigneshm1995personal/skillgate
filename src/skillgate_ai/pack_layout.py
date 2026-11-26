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


def _classifier_base(realpath: str) -> Path | None:
    if ".." in Path(realpath).parts:
        return None
    try:
        base = Path(realpath)
        if not base.is_absolute():
            return None
        return base
    except (OSError, ValueError):
        return None


def _named_child(parent: Path, name: str) -> Path | None:
    try:
        for child in parent.iterdir():
            if child.name == name:
                return child
    except OSError:
        return None
    return None


def _has_skill_pack_layout(base: Path) -> bool:
    skill = _named_child(base, "SKILL.md")
    evals = _named_child(base, "evals")
    if skill is None or evals is None:
        return False
    try:
        return skill.is_file() and evals.is_dir()
    except OSError:
        return False


def _has_skills_child(base: Path) -> bool:
    child = _named_child(base, "skills")
    if child is None:
        return False
    try:
        return child.is_dir()
    except OSError:
        return False


def _has_keys_child(base: Path) -> bool:
    gate = _named_child(base, ".skillgate")
    if gate is None:
        return False
    keys = _named_child(gate, "keys")
    if keys is None:
        return False
    try:
        return keys.is_file()
    except OSError:
        return False


def layout_has_skills_dir(root_real: str) -> bool:
    return discovery_has_skills_dir(Path(root_real))


def layout_skill_pack_at_root(root_real: str) -> bool:
    return discovery_skill_pack_dir(Path(root_real))


def layout_keys_file(root_real: str) -> bool:
    return discovery_keys_file(Path(root_real))


def layout_is_directory(root_real: str) -> bool:
    return discovery_is_directory(Path(root_real))


def layout_pack_markers(root_real: str) -> tuple[bool, bool, bool]:
    return discovery_pack_markers(Path(root_real))


def discovery_skill_pack_dir(candidate: Path) -> bool:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        base = _classifier_base(cand)
        if base is None:
            return False
        return _has_skill_pack_layout(base)
    except (OSError, ValueError):
        return False


def discovery_has_skills_dir(candidate: Path) -> bool:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        base = _classifier_base(cand)
        if base is None:
            return False
        return _has_skills_child(base)
    except OSError:
        return False


def discovery_keys_file(candidate: Path) -> bool:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        base = _classifier_base(cand)
        if base is None:
            return False
        return _has_keys_child(base)
    except OSError:
        return False


def discovery_is_directory(candidate: Path) -> bool:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        base = _classifier_base(cand)
        if base is None:
            return False
        try:
            return base.is_dir()
        except OSError:
            return False
    except OSError:
        return False


def discovery_pack_markers(candidate: Path) -> tuple[bool, bool, bool]:
    try:
        cand = os.path.realpath(os.fsdecode(candidate))
        base = _classifier_base(cand)
        if base is None:
            return False, False, False
        skill_ent = _named_child(base, "SKILL.md")
        evals_ent = _named_child(base, "evals")
        skill = skill_ent is not None and skill_ent.is_file()
        evals = evals_ent is not None and evals_ent.is_dir()
        pack = skill and evals
        return skill, evals, pack
    except OSError:
        return False, False, False
