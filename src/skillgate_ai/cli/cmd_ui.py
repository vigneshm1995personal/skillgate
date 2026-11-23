"""CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.config import load_env
from skillgate_ai.errors import SkillGateError
from skillgate_ai.paths import project_root


def ui_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address (default loopback)"),
    port: int = typer.Option(8765, "--port", help="Port (default 8765)"),
    root: Path | None = typer.Option(None, "--root", help="Workspace root for browse/create"),
    pack: Path | None = typer.Option(None, "--pack", help="Open this pack instead of the picker"),
    open_browser: bool = typer.Option(False, "--open", help="Open the loopback URL in a browser"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Do not open a browser"),
) -> None:
    """Local React UI. No account. Run needs an agent (`skillgate login` or a key)."""
    from skillgate_ai.extras import UI_FEATURE, MissingExtraError, require_extra

    try:
        require_extra("ui", feature=UI_FEATURE)
    except MissingExtraError as exc:
        base.console.print(exc.render(), markup=False)
        raise typer.Exit(exc.exit_code) from None

    from skillgate_ai.server import serve_ui

    if port < 1 or port > 65535:
        base.console.print("Port must be between 1 and 65535.")
        raise typer.Exit(2)
    if pack is not None:
        workspace = pack.expanduser().resolve()
    else:
        workspace = (root or project_root()).expanduser().resolve()
    load_env(workspace)
    should_open = open_browser and not no_browser
    if host not in {"127.0.0.1", "localhost", "::1"}:
        base.console.print(
            "Warning: binding off loopback. This is still a local process with no auth — "
            "not the hosted Skill Gate app."
        )
    try:
        serve_ui(
            root=workspace,
            host=host,
            port=port,
            pack=pack,
            open_browser=should_open,
        )
    except SkillGateError as exc:
        base.console.print(exc.render(), markup=False)
        raise typer.Exit(exc.exit_code) from None
    except OSError as exc:
        base.console.print(f"Could not bind {host}:{port}: {exc}")
        base.console.print("Stop the other process, or pass --port with a free port.")
        raise typer.Exit(1) from exc
