"""Create a Skill Gate workspace and a new skill pack."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.scaffold import create_pack, scaffold_trigger_cases

IGNORE_LINE = ".skillgate/"


def init_workspace(root: str | Path) -> Path:
    dest = Path(root).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "skills").mkdir(parents=True, exist_ok=True)
    gitignore = dest / ".gitignore"
    if gitignore.is_file():
        text = gitignore.read_text(encoding="utf-8")
        if IGNORE_LINE not in text.splitlines() and IGNORE_LINE not in text:
            gitignore.write_text(text.rstrip() + "\n" + IGNORE_LINE + "\n", encoding="utf-8")
    else:
        gitignore.write_text(IGNORE_LINE + "\n", encoding="utf-8")
    return dest


def new_skill(root: str | Path, name: str) -> Path:
    workspace = init_workspace(root)
    dest = create_pack(workspace / "skills", name)
    scaffold_trigger_cases(dest)
    return dest
