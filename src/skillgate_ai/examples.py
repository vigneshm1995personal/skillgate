"""Packaged example skills (pdf / pdf-sabotaged) for `skillgate example`."""

from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path

from skillgate_ai.errors import SkillGateError

EXAMPLE_NAMES = ("pdf", "pdf-sabotaged")


def bundled_example(name: str) -> Path:
    slug = (name or "").strip()
    if slug not in EXAMPLE_NAMES:
        raise SkillGateError(
            f"Unknown example {slug!r}.",
            hint="Try `skillgate example pdf` or `skillgate example pdf-sabotaged`.",
        )
    try:
        packaged = files("skillgate_ai").joinpath("examples").joinpath(slug)
        path = Path(str(packaged))
        if (path / "SKILL.md").is_file():
            return path
    except (FileNotFoundError, ModuleNotFoundError, TypeError, ValueError):
        pass
    here = Path(__file__).resolve()
    repo = here.parents[2] / "skills" / slug
    if (repo / "SKILL.md").is_file():
        return repo
    raise SkillGateError(
        f"Example `{slug}` is not in this install.",
        hint="Reinstall skillgate-ai, or run from a clone of the repo.",
    )


def copy_example(name: str, dest: str | Path) -> Path:
    src = bundled_example(name)
    target = Path(dest).expanduser().resolve()
    if target.exists():
        raise SkillGateError(
            f"Folder already exists: {target}",
            hint="Pick an empty destination, or remove the folder first.",
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        src,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".skillgate", "*.jsonl"),
    )
    return target
