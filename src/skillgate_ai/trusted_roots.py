"""Map user pack targets onto fixed filesystem anchors (never user path as I/O base)."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from skillgate_ai.allow_root import allow_root_realpaths, record_matched_allow_root
from skillgate_ai.fs_anchor import FsAnchor
from skillgate_ai.paths import PathTraversalError, config_root_for, is_under_root

_OUTSIDE_PACK_ROOT_MSG = (
    "Path is outside the workspace, agent skill folders, config tree, or allow-root. "
    "For a pack elsewhere, run: skillgate check --allow-root <dir> "
    "or add an absolute path to ~/.skillgate/allow-root."
)


def _agent_roots() -> tuple[tuple[Callable[[], Path], FsAnchor], ...]:
    from skillgate_ai.deploy import (
        claude_skills_root,
        codex_skills_root,
        cursor_skills_root,
    )

    return (
        (cursor_skills_root, FsAnchor.AGENT_CURSOR),
        (codex_skills_root, FsAnchor.AGENT_CODEX),
        (claude_skills_root, FsAnchor.AGENT_CLAUDE),
    )


def workspace_anchor() -> Path:
    from skillgate_ai.paths import project_root

    return project_root().resolve()


def normalize_pack_target(skill_path: str | Path) -> Path:
    raw = str(skill_path)
    text = os.path.expanduser(raw) if raw.startswith("~") else raw
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    return Path(os.path.realpath(text))


def _rel_under_workspace_skills(rel: tuple[str, ...]) -> bool:
    if not rel:
        return False
    if rel[0] == "skills":
        return len(rel) <= 3
    if "skills" not in rel:
        return False
    return len(rel) - rel.index("skills") <= 2


def _prefix_sibling_of_gate(bound: Path, gate: Path) -> bool:
    """Detect ``/tmp/a`` vs ``/tmp/ab`` style prefix siblings around a workspace gate."""
    gate_text = os.path.normpath(os.path.realpath(str(gate)))
    bound_text = os.path.normpath(os.path.realpath(str(bound)))
    if bound_text == gate_text or bound_text.startswith(gate_text + os.sep):
        return False
    return bound_text.startswith(gate_text) or gate_text.startswith(bound_text + os.sep)


def pack_access_root(skill_path: str | Path) -> tuple[FsAnchor, tuple[str, ...]]:
    """Fixed anchor kind plus validated relative segments to the pack root."""
    resolved = normalize_pack_target(skill_path)
    from skillgate_ai.pack_layout import (
        loose_pack_mount_at,
        relative_segments_under,
        single_path_segment_name,
    )

    target = os.path.realpath(os.fsdecode(resolved))

    env_root = os.environ.get("SKILLGATE_ROOT")
    if env_root and ".." not in Path(env_root).parts:
        gate_real = os.path.realpath(env_root)
        gate = Path(gate_real)
        if is_under_root(resolved, gate):
            rel = relative_segments_under(gate_real, target)
            if rel is not None:
                workspace = workspace_anchor()
                if _prefix_sibling_of_gate(resolved, workspace) and (workspace != gate):
                    raise PathTraversalError("Path escapes the allowed root.")
                return FsAnchor.SKILLGATE_ENV, rel

    workspace = workspace_anchor()
    workspace_real = os.path.realpath(os.fsdecode(workspace))
    if is_under_root(resolved, workspace):
        rel = relative_segments_under(workspace_real, target)
        if rel is not None:
            if env_root:
                gate = Path(env_root).resolve()
                if _prefix_sibling_of_gate(resolved, gate):
                    raise PathTraversalError("Path escapes the allowed root.")
            from skillgate_ai.contained_fs import isdir_at

            pack_layout_ok = loose_pack_mount_at(FsAnchor.WORKSPACE, *rel) or isdir_at(
                FsAnchor.WORKSPACE, *rel, "evals"
            )
            under_skills = _rel_under_workspace_skills(rel) and pack_layout_ok
            shallow_pack = len(rel) <= 2 and pack_layout_ok
            if under_skills or shallow_pack:
                return FsAnchor.WORKSPACE, rel

    config = config_root_for(None)
    config_real = os.path.realpath(os.fsdecode(config))
    if config_real != workspace_real and is_under_root(resolved, config):
        rel = relative_segments_under(config_real, target)
        if rel is not None:
            from skillgate_ai.pack_layout import discovery_has_skills_dir, discovery_keys_file

            if discovery_has_skills_dir(config) or discovery_keys_file(config):
                return FsAnchor.CONFIG, rel

    for getter, agent_anchor in _agent_roots():
        try:
            agent_real = os.path.realpath(os.fsdecode(getter().resolve()))
        except OSError:
            continue
        parts = relative_segments_under(agent_real, target)
        if parts is None or len(parts) != 1:
            continue
        name = parts[0]
        if not single_path_segment_name(name):
            continue
        try:
            if loose_pack_mount_at(agent_anchor, name):
                return agent_anchor, (name,)
        except OSError:
            continue

    for allow in allow_root_realpaths():
        parts = relative_segments_under(allow, target)
        if parts is None:
            continue
        record_matched_allow_root(allow)
        try:
            if loose_pack_mount_at(FsAnchor.ALLOW_ROOT, *parts):
                return FsAnchor.ALLOW_ROOT, parts
        except (PathTraversalError, OSError):
            continue

    raise PathTraversalError(_OUTSIDE_PACK_ROOT_MSG)


def skill_pack_root_from_access(skill_path: str | Path) -> Path:
    from skillgate_ai.paths import filesystem_path_under

    anchor, parts = pack_access_root(skill_path)
    if not parts:
        return Path(filesystem_path_under(anchor))
    return Path(filesystem_path_under(anchor, *parts))
