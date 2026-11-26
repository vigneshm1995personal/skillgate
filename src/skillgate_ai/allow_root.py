"""Explicit user opt-in directory for pack reads (never from pack or repo env)."""

from __future__ import annotations

import os
from pathlib import Path

from skillgate_ai.path_traversal import PathTraversalError

ALLOW_ROOT_FILENAME = "allow-root"

_cli_allow_root: str | None = None
_matched_allow_root: str | None = None


def set_cli_allow_root(path: str | Path | None) -> None:
    """Record ``--allow-root`` for the current CLI process (cleared when ``None``)."""
    global _cli_allow_root
    if path is None:
        _cli_allow_root = None
        return
    text = os.path.expanduser(str(path))
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _cli_allow_root = os.path.realpath(text)


def get_cli_allow_root() -> str | None:
    return _cli_allow_root


def read_user_allow_root_file() -> str | None:
    """Read ``~/.skillgate/allow-root`` only (never project ``.skillgate``)."""
    path = Path.home() / ".skillgate" / ALLOW_ROOT_FILENAME
    try:
        if not path.is_file():
            return None
        line = path.read_text(encoding="utf-8").splitlines()[0].strip()
    except OSError:
        return None
    if not line or ".." in Path(line).parts:
        return None
    try:
        expanded = os.path.expanduser(line)
        return os.path.realpath(expanded)
    except OSError:
        return None


def allow_root_realpaths() -> tuple[str, ...]:
    """All user-approved allow roots for this process (CLI flag + home file)."""
    paths: list[str] = []
    if _cli_allow_root:
        paths.append(_cli_allow_root)
    from_file = read_user_allow_root_file()
    if from_file and from_file not in paths:
        paths.append(from_file)
    return tuple(paths)


def record_matched_allow_root(realpath: str) -> None:
    """Remember which allow-root matched ``pack_access_root`` for ``anchor_base``."""
    global _matched_allow_root
    _matched_allow_root = realpath


def matched_allow_root_base() -> str | None:
    return _matched_allow_root
