"""Fixed filesystem anchors for pack I/O (never a user-derived path string)."""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path

from skillgate_ai.path_traversal import PathTraversalError


class FsAnchor(Enum):
    WORKSPACE = "workspace"
    SKILLGATE_ENV = "skillgate_env"
    CONFIG = "config"
    ALLOW_ROOT = "allow_root"
    AGENT_CURSOR = "agent_cursor"
    AGENT_CODEX = "agent_codex"
    AGENT_CLAUDE = "agent_claude"


def anchor_base(anchor: FsAnchor) -> str:
    """Resolved absolute base path for a fixed anchor (CodeQL-safe I/O root)."""
    if anchor is FsAnchor.WORKSPACE:
        from skillgate_ai.paths import project_root

        base = project_root()
        text = os.fsdecode(base)
        if ".." in Path(text).parts:
            raise PathTraversalError("Path escapes the allowed root.")
        return os.path.realpath(text)
    if anchor is FsAnchor.SKILLGATE_ENV:
        env = os.environ.get("SKILLGATE_ROOT")
        if not env or ".." in Path(env).parts:
            raise PathTraversalError("Path escapes the allowed root.")
        return os.path.realpath(env)
    if anchor is FsAnchor.CONFIG:
        from skillgate_ai.paths import config_root_for

        base = config_root_for(None)
        text = os.fsdecode(base)
        if ".." in Path(text).parts:
            raise PathTraversalError("Path escapes the allowed root.")
        return os.path.realpath(text)
    if anchor is FsAnchor.ALLOW_ROOT:
        from skillgate_ai.allow_root import matched_allow_root_base

        allow_base = matched_allow_root_base()
        if not allow_base:
            raise PathTraversalError("Path escapes the allowed root.")
        return allow_base
    if anchor is FsAnchor.AGENT_CURSOR:
        from skillgate_ai.deploy import cursor_skills_root

        return os.path.realpath(str(cursor_skills_root()))
    if anchor is FsAnchor.AGENT_CODEX:
        from skillgate_ai.deploy import codex_skills_root

        return os.path.realpath(str(codex_skills_root()))
    if anchor is FsAnchor.AGENT_CLAUDE:
        from skillgate_ai.deploy import claude_skills_root

        return os.path.realpath(str(claude_skills_root()))
    raise PathTraversalError("Path escapes the allowed root.")
