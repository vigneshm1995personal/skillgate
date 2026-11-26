"""Map user pack targets onto fixed filesystem anchors (never user path as I/O base)."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from skillgate_ai.deploy import claude_skills_root, codex_skills_root, cursor_skills_root
from skillgate_ai.paths import PathTraversalError, is_under_root

_AGENT_GETTERS: tuple[Callable[[], Path], ...] = (
    cursor_skills_root,
    codex_skills_root,
    claude_skills_root,
)


def _discover_workspace_from_cwd() -> Path:
    from skillgate_ai.paths import _has_workspace_skills, is_skill_pack, project_root

    if os.environ.get("SKILLGATE_ROOT"):
        return project_root().resolve()
    cwd = Path.cwd()
    workspace = None
    pack = None
    for candidate in (cwd, *cwd.parents):
        if workspace is None and _has_workspace_skills(candidate):
            workspace = candidate
            break
        if pack is None and is_skill_pack(candidate):
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


def register_standalone_pack_for_cli(pack: str | Path) -> None:
    """When ``check <packdir>`` is outside the cwd workspace, pin ``SKILLGATE_ROOT`` to that pack."""
    resolved = normalize_pack_target(pack)
    workspace = _discover_workspace_from_cwd()
    if is_under_root(resolved, workspace):
        return
    from skillgate_ai.contained_fs import isdir_at, isfile_at

    if not isfile_at(resolved, "SKILL.md"):
        if not isdir_at(resolved, "evals"):
            return
    os.environ["SKILLGATE_ROOT"] = os.fsdecode(resolved)


def _prefix_sibling_of_gate(bound: Path, gate: Path) -> bool:
    """Detect ``/tmp/a`` vs ``/tmp/ab`` style prefix siblings around a workspace gate."""
    gate_text = os.path.normpath(os.path.realpath(str(gate)))
    bound_text = os.path.normpath(os.path.realpath(str(bound)))
    if bound_text == gate_text or bound_text.startswith(gate_text + os.sep):
        return False
    return bound_text.startswith(gate_text) or gate_text.startswith(bound_text + os.sep)


def _is_pack_mount(resolved: Path) -> bool:
    from skillgate_ai.contained_fs import isdir_at, isfile_at
    from skillgate_ai.paths import is_skill_pack

    return (
        is_skill_pack(resolved)
        or isfile_at(resolved, "SKILL.md")
        or isfile_at(resolved, "evals", "cases.yaml")
        or isdir_at(resolved, "evals")
        or isdir_at(resolved, "scripts")
    )


def pack_access_root(skill_path: str | Path) -> tuple[Path, tuple[str, ...]]:
    """Fixed anchor plus relative segments; anchor is never the raw user path alone."""
    resolved = normalize_pack_target(skill_path)
    from skillgate_ai.paths import _has_workspace_skills, config_root_for

    workspace = workspace_anchor()
    if is_under_root(resolved, workspace):
        rel = resolved.relative_to(workspace)
        return workspace, rel.parts

    for getter in _AGENT_GETTERS:
        try:
            agent = getter().resolve()
        except OSError:
            continue
        if resolved.parent.resolve() != agent:
            continue
        from skillgate_ai.contained_fs import isdir_at, isfile_at

        name = resolved.name
        if name and isdir_at(agent, name) and isfile_at(agent, name, "SKILL.md"):
            return agent, (name,)

    bound = config_root_for(resolved).resolve()
    if _has_workspace_skills(bound) and is_under_root(resolved, bound):
        rel = resolved.relative_to(bound)
        return bound, rel.parts

    if is_under_root(resolved, bound) and _is_pack_mount(resolved):
        env_root = os.environ.get("SKILLGATE_ROOT")
        if env_root:
            gate = Path(env_root).resolve()
            if _has_workspace_skills(gate) and _prefix_sibling_of_gate(bound, gate):
                raise PathTraversalError("Path escapes the allowed root.")
        if resolved == bound:
            return bound, ()
        rel = resolved.relative_to(bound)
        return bound, rel.parts

    env_root = os.environ.get("SKILLGATE_ROOT")
    if env_root:
        gate = Path(env_root).resolve()
        if _has_workspace_skills(gate) and not is_under_root(resolved, gate):
            raise PathTraversalError("Path escapes the allowed root.")
        if is_under_root(resolved, gate):
            rel = resolved.relative_to(gate)
            return gate, rel.parts

    raw = str(skill_path)
    candidate = Path(os.path.expanduser(raw) if raw.startswith("~") else raw)
    if candidate.is_absolute() and ".." not in candidate.parts and not candidate.exists():
        return candidate.resolve(), ()

    raise PathTraversalError("Path escapes the allowed root.")


def skill_pack_root_from_access(skill_path: str | Path) -> Path:
    from skillgate_ai.paths import filesystem_path_under

    anchor, parts = pack_access_root(skill_path)
    if not parts:
        return anchor
    return Path(filesystem_path_under(anchor, *parts))