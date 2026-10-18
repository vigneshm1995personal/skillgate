"""Packaged example skills for `skillgate example` and `skillgate examples`."""

from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path
from typing import Any

from skillgate_ai.errors import SkillGateError

EXAMPLE_NAMES = ("pdf", "pdf-sabotaged")
DATASET_EXAMPLES = (
    "json-response",
    "json-response-sabotaged",
    "readme-writer",
    "log-summarizer",
    "sql-writer",
    "receipt-extractor",
)
BUNDLED_EXAMPLES = EXAMPLE_NAMES + DATASET_EXAMPLES
_SKIP_DIRS = {".git", "__pycache__", ".skillgate"}


def bundled_example(name: str) -> Path:
    slug = (name or "").strip()
    if slug not in BUNDLED_EXAMPLES:
        raise SkillGateError(
            f"Unknown example {slug!r}.",
            hint="Try `skillgate examples list` or `skillgate example pdf`.",
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


def list_examples() -> list[dict[str, str]]:
    from skillgate_ai.ingest import ingest_skill

    rows: list[dict[str, str]] = []
    for name in DATASET_EXAMPLES:
        loaded = ingest_skill(bundled_example(name), strict=False)
        rows.append(
            {
                "name": name,
                "description": (loaded.description or "").strip(),
            }
        )
    return rows


def _example_files(src: Path) -> list[tuple[Path, Path]]:
    found: list[tuple[Path, Path]] = []
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix == ".jsonl" or path.name.endswith(".jsonl"):
            continue
        found.append((rel, path))
    return found


def install_examples(
    dest_root: str | Path,
    names: list[str] | tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Copy dataset examples into a skills folder. Existing files stay as they are."""
    chosen = tuple(names) if names else DATASET_EXAMPLES
    if not chosen:
        raise SkillGateError(
            "Name an example to install.",
            hint="Run `skillgate examples list`.",
        )
    unknown = [item for item in chosen if item not in DATASET_EXAMPLES]
    if unknown:
        raise SkillGateError(
            f"Unknown example {unknown[0]!r}.",
            hint="Run `skillgate examples list`.",
        )
    root = Path(dest_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    installed: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    for name in chosen:
        src = bundled_example(name)
        target = root / name
        copied = 0
        for rel, path in _example_files(src):
            dest = target / rel
            if dest.exists():
                skipped.append({"name": name, "path": str(dest)})
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            copied += 1
        installed.append({"name": name, "path": str(target), "files": copied})
    return {"installed": installed, "skipped": skipped}


def copy_example(name: str, dest: str | Path) -> Path:
    slug = (name or "").strip()
    if slug not in EXAMPLE_NAMES:
        raise SkillGateError(
            f"Unknown example {slug!r}.",
            hint="Try `skillgate example pdf` or `skillgate example pdf-sabotaged`.",
        )
    src = bundled_example(slug)
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
