"""CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.errors import SkillGateError
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.paths import is_skill_pack, resolve_user_path
from skillgate_ai.suite import discover_suites


def deploy(
    pack: Path = typer.Argument(..., help="Gated skill pack to copy"),
    target: str | None = typer.Option(None, "--target", help="cursor | claude | codex (comma ok)"),
    targets: str | None = typer.Option(
        None, "--targets", help="Same as --target; one name or a comma list"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help=(
            "Install even if the latest check did not pass. Does not skip a skill "
            "that has never been checked."
        ),
    ),
) -> None:
    """Copy a skill pack into a local agent skills directory.

    Refuses unless this pack already has a passing check and an agent is
    available (API key or `skillgate login`). Does not run check. Copies skill
    files only (not evals/). --force only overrides a red latest check; it does
    not skip a missing agent.
    """
    from skillgate_ai.config import get_llm_config, missing_key_error
    from skillgate_ai.deploy import get_adapter, require_passing_check
    from skillgate_ai.history import append_deploy

    root = base._boot()
    path = resolve_user_path(pack, root)
    selected = base._parse_targets(target, targets, default="cursor")
    try:
        adapters = [get_adapter(name) for name in selected]
        loaded = ingest_skill(path)
        require_passing_check(path, name=loaded.name, force=force)
        if not get_llm_config(root).has_any_key:
            raise missing_key_error()
        for adapter in adapters:
            result = adapter.install(skill=loaded, source=path, force=force)
            base.console.print(result["message"])
            append_deploy(
                path,
                target=adapter.id,
                status=result.get("status") or "installed",
                file_count=result.get("file_count"),
                mode="local",
            )
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None


def sync(
    repo: str = typer.Option(..., "--repo", help="Git repo URL with skills/ inside"),
    target: str | None = typer.Option(None, "--target", help="Same as --targets"),
    targets: str | None = typer.Option(
        None, "--targets", help="Comma-separated targets (default cursor,codex,claude)"
    ),
    interval: int = typer.Option(0, "--interval", help="Seconds between syncs (0 = once)"),
    install_launchd: bool = typer.Option(
        False, "--install-launchd", help="Install a macOS LaunchAgent for sync"
    ),
) -> None:
    """Pull a skills repo and copy its skills into local agent dirs."""
    from skillgate_ai.sync import install_launchd_plist, run_sync_loop, sync_once

    selected = base._parse_targets(target, targets, default="cursor,codex,claude")
    try:
        if install_launchd:
            path = install_launchd_plist(repo_url=repo, targets=selected, interval=interval)
            base.console.print(f"Installed sync LaunchAgent at {path}")
            raise typer.Exit(0)
        if interval and interval > 0:
            run_sync_loop(repo, targets=selected, interval=interval)
        else:
            result = sync_once(repo, targets=selected)
            for name in result.get("skipped") or []:
                base.console.print(f"skipped {name}: latest check did not pass")
            for name in result.get("synced") or []:
                base.console.print(f"synced  {name}")
            for target_key, summary in result["targets"].items():
                base.console.print(
                    f"{target_key}  installed={summary['installed']} "
                    f"removed={summary['removed']} → {summary['target_root']}"
                )
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from exc


def connect(
    url: str = typer.Option(..., "--url", help="Hosted Skill Gate URL"),
    code: str = typer.Option(..., "--code", help="One-time pairing code"),
    name: str | None = typer.Option(None, "--name", help="Nickname for this Mac"),
) -> None:
    """Pair this Mac with a hosted Skill Gate (stores a token at 0600)."""
    from skillgate_ai.helper import connect as connect_helper

    try:
        config = connect_helper(url, code, name)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from exc
    base.console.print(f"Connected {config['name']} ({config['device_id']}).")
    base.console.print("Run `skillgate helper` to receive deploy jobs.")


def helper(
    once: bool = typer.Option(False, "--once", help="Poll once and exit"),
    install_launchd: bool = typer.Option(
        False, "--install-launchd", help="Install a macOS LaunchAgent for the helper"
    ),
) -> None:
    """Poll a hosted Skill Gate for deploy jobs and install skills (outbound only)."""
    from skillgate_ai.helper import (
        install_launchd_plist,
        load_helper_config,
        run_helper,
    )

    try:
        if install_launchd:
            path = install_launchd_plist()
            base.console.print(f"Installed helper LaunchAgent at {path}")
            raise typer.Exit(0)
        config = load_helper_config()
        if config is None:
            raise SkillGateError(
                "Not connected. Run `skillgate connect --url <hosted> --code <code>` first."
            )
        run_helper(config, once=once)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from exc


def list_assets() -> None:
    """Show skills/ and evals/ (skill-first paths)."""
    root = base._boot()
    base.console.print(f"root  {root}")
    skills_root = root / "skills"
    if skills_root.is_dir():
        base.console.print("skills/")
        for child in sorted(skills_root.iterdir()):
            if child.is_dir() and (child / "SKILL.md").is_file():
                base.console.print(f"  {child.name}")
    elif is_skill_pack(root):
        base.console.print(f"pack  {root.name}")
    evals_root = root / "evals"
    if evals_root.is_dir():
        cases = evals_root / "cases.yaml"
        if cases.is_file():
            base.console.print("evals/cases.yaml")
        base.console.print("evals/")
        for suite in discover_suites(evals_root):
            base.console.print(f"  {suite.name}")
