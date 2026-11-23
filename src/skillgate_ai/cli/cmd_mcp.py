"""skillgate mcp — local MCP server over stdio."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.config import load_env
from skillgate_ai.errors import SkillGateError
from skillgate_ai.paths import project_root


def mcp_cmd(
    root: Path | None = typer.Option(
        None, "--root", envvar="SKILLGATE_ROOT", help="Project root the tools act on"
    ),
) -> None:
    """Local MCP server (stdio) for agents. No account. Checks need `skillgate login` or a key."""
    from skillgate_ai.extras import MCP_FEATURE, MissingExtraError, require_extra

    try:
        require_extra("mcp", feature=MCP_FEATURE)
    except MissingExtraError as exc:
        typer.echo(exc.render(), err=True)
        raise typer.Exit(exc.exit_code) from None
    workspace = (root or project_root()).expanduser().resolve()
    if not workspace.is_dir():
        typer.echo(f"Root {workspace} is not a folder.", err=True)
        raise typer.Exit(2)
    load_env(workspace)
    from skillgate_ai.mcp.server import serve

    try:
        serve(workspace)
    except SkillGateError as exc:
        typer.echo(exc.render(), err=True)
        raise typer.Exit(exc.exit_code) from None
