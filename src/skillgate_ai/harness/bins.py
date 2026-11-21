"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

from skillgate_ai.ingest import Skill


def _resolve_agent_bin(preferred: str) -> str | None:
    """Find `agent` (official) or `cursor-agent` alias, including ~/.local/bin."""
    names: list[str] = []
    if preferred:
        names.append(preferred)
    for name in ("agent", "cursor-agent"):
        if name not in names:
            names.append(name)
    for name in names:
        found = shutil.which(name)
        if found:
            return found
        if _looks_like_bin_path(name):
            found = _executable_path(Path(name).expanduser())
            if found:
                return found
    home_local = Path.home() / ".local" / "bin"
    for name in ("agent", "cursor-agent"):
        found = _executable_path(home_local / name)
        if found:
            return found
    return None


def _executable_path(path: Path) -> str | None:
    if path.is_file() and os.access(path, os.X_OK):
        return str(path)
    return None


def _looks_like_bin_path(name: str) -> bool:
    return name.startswith(("~", ".", "/")) or "/" in name


def _resolve_codex_bin(preferred: str) -> str | None:
    if preferred:
        found = shutil.which(preferred)
        if found:
            return found
        if _looks_like_bin_path(preferred):
            found = _executable_path(Path(preferred).expanduser())
            if found:
                return found
    found = shutil.which("codex")
    if found:
        return found
    return _executable_path(Path.home() / ".local" / "bin" / "codex")


def _resolve_claude_bin(preferred: str) -> str | None:
    if preferred:
        found = shutil.which(preferred)
        if found:
            return found
        if _looks_like_bin_path(preferred):
            found = _executable_path(Path(preferred).expanduser())
            if found:
                return found
    return shutil.which("claude")


def _pinned_has_agent_entry(skills: list[Skill], pinned_skill: str) -> bool:
    """True when the pinned skill pack ships ``scripts/agent_entry.py``."""
    for skill in skills:
        if skill.name == pinned_skill:
            return (skill.path / "scripts" / "agent_entry.py").is_file()
    return False
