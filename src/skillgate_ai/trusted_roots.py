"""Map user pack targets onto fixed filesystem anchors (never user path as I/O base)."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from skillgate_ai.deploy import claude_skills_root, codex_skills_root, cursor_skills_root
from skillgate_ai.fs_anchor import FsAnchor
from skillgate_ai.paths import PathTraversalError, is_under_root

_AGENT_GETTERS: tuple[tuple[Callable[[], Path], FsAnchor], ...] = (
    (cursor_skills_root, FsAnchor.AGENT_CURSOR),
    (codex_skills_root, FsAnchor.AGENT_CODEX),
    (claude_skills_root, FsAnchor.AGENT_CLAUDE),
)


def _discover_workspace_from_cwd() -> Path:
    from skillgate_ai.paths import _has_workspace_skills, project_root

    if os.environ.get("SKILLGATE_ROOT"):
        return project_root().resolve()
    cwd = Path.cwd()
    workspace = None
    pack = None
    for candidate in (cwd, *cwd.parents):
        if workspace is None and _has_workspace_skills(candidate):
            workspace = candidate
            break
        if pack is None:
            from skillgate_ai.pack_layout import discovery_skill_pack_dir

            if discovery_skill_pack_dir(candidate):
                pack = candidate
    if workspace is not None:
        return workspace.resolve()
    if pack is not None:
        return pack.resolve()
    return cwd.resolve()


def workspace_anchor() -> Path:
    from skillgate_ai.paths import project_root

    return project_root().resolve()


def normalize_pack_target(skill_path: str | Path) -> Path:
    raw = str(skill_path)
    text = os.path.expanduser(raw) if raw.startswith("~") else raw
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    return Path(os.path.realpath(text))


def _pin_skillgate_root(resolved: Path) -> None:
    os.environ["SKILLGATE_ROOT"] = os.fsdecode(resolved)


def register_standalone_pack_for_cli(pack: str | Path) -> None:
    """Set ``SKILLGATE_ROOT`` for standalone ``check <packdir>`` outside the cwd workspace."""
    resolved = normalize_pack_target(pack)
    workspace = _discover_workspace_from_cwd()
    if is_under_root(resolved, workspace):
        return
    if not _is_pack_mount(resolved):
        return
    _pin_skillgate_root(resolved)


def _prefix_sibling_of_gate(bound: Path, gate: Path) -> bool:
    """Detect ``/tmp/a`` vs ``/tmp/ab`` style prefix siblings around a workspace gate."""
    gate_text = os.path.normpath(os.path.realpath(str(gate)))
    bound_text = os.path.normpath(os.path.realpath(str(bound)))
    if bound_text == gate_text or bound_text.startswith(gate_text + os.sep):
        return False
    return bound_text.startswith(gate_text) or gate_text.startswith(bound_text + os.sep)


def _is_pack_mount(resolved: Path) -> bool:
    from skillgate_ai.pack_layout import (
        discovery_skill_pack_dir,
        loose_pack_mount_at,
        relative_segments_under,
    )

    if discovery_skill_pack_dir(resolved):
        return True
    target = os.path.realpath(os.fsdecode(resolved))
    ws = os.path.realpath(os.fsdecode(workspace_anchor()))
    parts = relative_segments_under(ws, target)
    if parts is not None:
        return loose_pack_mount_at(FsAnchor.WORKSPACE, *parts)
    env = os.environ.get("SKILLGATE_ROOT")
    if env and ".." not in Path(env).parts:
        gate = os.path.realpath(env)
        parts = relative_segments_under(gate, target)
        if parts is not None:
            return loose_pack_mount_at(FsAnchor.SKILLGATE_ENV, *parts)
    from skillgate_ai.pack_layout import single_path_segment_name

    for getter, agent_anchor in _AGENT_GETTERS:
        try:
            agent = os.path.realpath(os.fsdecode(getter().resolve()))
        except OSError:
            continue
        parts = relative_segments_under(agent, target)
        if parts is not None and len(parts) == 1 and single_path_segment_name(parts[0]):
            return loose_pack_mount_at(agent_anchor, *parts)
    from skillgate_ai.pack_layout import loose_mount_at_pinned_root

    return loose_mount_at_pinned_root(target)


def pack_access_root(skill_path: str | Path) -> tuple[FsAnchor, tuple[str, ...]]:
    """Fixed anchor kind plus validated relative segments to the pack root."""
    resolved = normalize_pack_target(skill_path)
    from skillgate_ai.pack_layout import (
        relative_segments_under,
        single_path_segment_name,
        strict_skill_pack_at,
    )
    from skillgate_ai.paths import _has_workspace_skills, config_root_for

    target = os.path.realpath(os.fsdecode(resolved))
    env_root = os.environ.get("SKILLGATE_ROOT")
    if env_root and ".." not in Path(env_root).parts:
        gate = Path(env_root).resolve()
        gate_real = os.path.realpath(env_root)
        if is_under_root(resolved, gate):
            rel = relative_segments_under(gate_real, target)
            if rel is not None:
                return FsAnchor.SKILLGATE_ENV, rel

    workspace = workspace_anchor()
    workspace_real = os.path.realpath(os.fsdecode(workspace))
    if is_under_root(resolved, workspace):
        rel = relative_segments_under(workspace_real, target)
        if rel is not None:
            return FsAnchor.WORKSPACE, rel

    for getter, agent_anchor in _AGENT_GETTERS:
        try:
            agent_real = os.path.realpath(os.fsdecode(getter().resolve()))
        except OSError:
            continue
        parts = relative_segments_under(agent_real, os.path.realpath(os.fsdecode(resolved)))
        if parts is None or len(parts) != 1:
            continue
        name = parts[0]
        if not single_path_segment_name(name):
            continue
        try:
            if strict_skill_pack_at(agent_anchor, name):
                return agent_anchor, (name,)
        except OSError:
            continue

    bound = Path(os.path.realpath(os.fsdecode(config_root_for(resolved))))
    bound_real = os.path.realpath(os.fsdecode(bound))
    if _has_workspace_skills(bound) and is_under_root(resolved, bound):
        rel = relative_segments_under(bound_real, target)
        if rel is not None:
            if bound != workspace_anchor():
                _pin_skillgate_root(bound)
                return FsAnchor.SKILLGATE_ENV, rel
            return FsAnchor.WORKSPACE, rel

    if is_under_root(resolved, bound) and _is_pack_mount(resolved):
        env_root = os.environ.get("SKILLGATE_ROOT")
        if env_root:
            gate = Path(env_root).resolve()
            if _has_workspace_skills(gate) and _prefix_sibling_of_gate(bound, gate):
                raise PathTraversalError("Path escapes the allowed root.")
        _pin_skillgate_root(bound if resolved == bound else resolved)
        gate_real = os.path.realpath(os.environ["SKILLGATE_ROOT"])
        rel = relative_segments_under(gate_real, target)
        if rel is not None:
            return FsAnchor.SKILLGATE_ENV, rel
    if resolved.is_absolute() and ".." not in resolved.parts and not os.path.exists(target):
        _pin_skillgate_root(resolved)
        return FsAnchor.SKILLGATE_ENV, ()

    if env_root:
        gate = Path(env_root).resolve()
        if _has_workspace_skills(gate) and not is_under_root(resolved, gate):
            raise PathTraversalError("Path escapes the allowed root.")

    if ".." not in resolved.parts and (resolved.is_dir() or _is_pack_mount(resolved)):
        _pin_skillgate_root(resolved)
        return FsAnchor.SKILLGATE_ENV, ()

    raise PathTraversalError("Path escapes the allowed root.")


def skill_pack_root_from_access(skill_path: str | Path) -> Path:
    from skillgate_ai.paths import filesystem_path_under

    anchor, parts = pack_access_root(skill_path)
    if not parts:
        return Path(filesystem_path_under(anchor))
    return Path(filesystem_path_under(anchor, *parts))
