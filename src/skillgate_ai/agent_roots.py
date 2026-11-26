"""Agent skill install directories (env override or default under user home)."""

from __future__ import annotations

import os
from pathlib import Path


def _override_root(env_var: str) -> Path | None:
    env = os.environ.get(env_var, "").strip()
    return Path(env).expanduser().resolve() if env else None


def cursor_skills_root() -> Path:
    return (
        _override_root("SKILLGATE_CURSOR_SKILLS") or (Path.home() / ".cursor" / "skills").resolve()
    )


def codex_skills_root() -> Path:
    return _override_root("SKILLGATE_CODEX_SKILLS") or (Path.home() / ".codex" / "skills").resolve()


def claude_skills_root() -> Path:
    return (
        _override_root("SKILLGATE_CLAUDE_SKILLS") or (Path.home() / ".claude" / "skills").resolve()
    )
