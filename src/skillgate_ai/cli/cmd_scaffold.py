"""CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.errors import SkillGateError


def init_cmd(
    dest: Path | None = typer.Argument(None, help="Workspace folder (default: current directory)"),
) -> None:
    """Create a Skill Gate workspace (`skills/` and ignore `.skillgate/`)."""
    from skillgate_ai.workspace import init_workspace

    root = (dest or Path.cwd()).expanduser().resolve()
    try:
        init_workspace(root)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    except OSError as exc:
        base.console.print("Couldn't create that folder.")
        if exc.strerror:
            base.console.print(exc.strerror)
        raise typer.Exit(1) from None
    base.console.print(f"Workspace ready at {root}")


def new_cmd(
    name: str = typer.Argument(..., help="Skill folder name (lowercase, hyphens)"),
) -> None:
    """Create `skills/NAME` with SKILL.md and starter checks (same as the UI)."""
    from skillgate_ai.paths import project_root
    from skillgate_ai.workspace import new_skill

    root = project_root()
    try:
        dest = new_skill(root, name)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    base.console.print(f"Created {dest}")


def example_cmd(
    name: str = typer.Argument(..., help="pdf | pdf-sabotaged"),
    dest: Path | None = typer.Option(None, "--dest", help="Folder to write (default: skills/NAME)"),
) -> None:
    """Copy a packaged example skill into this folder."""
    from skillgate_ai.examples import copy_example

    root = base._boot()
    target = (dest or (root / "skills" / name)).expanduser().resolve()
    try:
        written = copy_example(name, target)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    base.console.print(f"Wrote {written}")


def examples_list_cmd() -> None:
    """List example skills you can install."""
    from skillgate_ai.examples import list_examples

    base._boot()
    for row in list_examples():
        base.console.print(f"{row['name']}\t{row['description']}")


def examples_install_cmd(
    name: str | None = typer.Argument(
        None, help="One example. Omit to install every dataset example."
    ),
    dest: Path | None = typer.Option(None, "--dest", help="Skills folder (default: ./skills)"),
) -> None:
    """Copy example skills into the skills folder. Existing files stay as they are."""
    from skillgate_ai.examples import install_examples
    from skillgate_ai.paths import config_root_for

    base._boot()
    target = (dest or (config_root_for(Path.cwd()) / "skills")).expanduser().resolve()
    try:
        result = install_examples(target, [name] if name else None)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    for row in result["installed"]:
        base.console.print(f"Installed {row['name']} ({row['files']} files) → {row['path']}")
    skipped = result["skipped"]
    if skipped:
        base.console.print(f"Left {len(skipped)} existing file(s) in place.")
