"""CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

import skillgate_ai.cli.base as base
from skillgate_ai import __version__
from skillgate_ai.errors import SkillGateError
from skillgate_ai.ingest import ingest_skill


def version() -> None:
    """Print the CLI version."""
    base.console.print(__version__)


def _print_agent_status(*, json_out: bool) -> None:
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.harness import format_harness_status, harness_auth_status

    rows = harness_auth_status(get_llm_config(base._boot()))
    if json_out:
        base._emit_json({"harnesses": rows})
        return
    base.console.print(format_harness_status(rows))


def _login_targets(agent: str | None) -> list[str]:
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.harness import harness_auth_status, normalize_login_agent

    if agent:
        kind = normalize_login_agent(agent)
        if kind is None:
            raise typer.BadParameter("Use cursor, claude, or codex.")
        return [kind]
    rows = harness_auth_status(get_llm_config(base._boot()))
    missing = [str(row["agent"]) for row in rows if row["installed"] and row["auth"] == "none"]
    if missing:
        if base._stdin_is_tty() and len(missing) > 1:
            names = ", ".join(missing)
            picked = (
                typer.prompt(
                    f"Sign in ({names}, or all)",
                    default="all",
                )
                .strip()
                .lower()
            )
            if picked in {"all", "*", "missing"}:
                return missing
            kind = normalize_login_agent(picked)
            if kind is None:
                raise typer.BadParameter("Use cursor, claude, codex, or all.")
            return [kind]
        return missing
    return []


def login(
    agent: str | None = typer.Argument(
        None, help="cursor | claude | codex. Omit to sign in missing agents."
    ),
    status: bool = typer.Option(
        False, "--status", help="Show installed / logged in / API key / none."
    ),
    json_out: bool = typer.Option(False, "--json", help="Machine JSON"),
    force: bool = typer.Option(
        False, "--force", help="Run the official login even if already signed in."
    ),
) -> None:
    """Sign in with an agent using that agent's official login."""
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.harness import (
        AUTH_CLI_LOGIN,
        cursor_auth_kind,
        format_harness_status,
        harness_auth_status,
        normalize_login_agent,
        run_official_login,
    )
    from skillgate_ai.harness.auth import claude_auth_kind

    root = base._boot()
    if status:
        _print_agent_status(json_out=json_out)
        raise typer.Exit()
    try:
        targets = _login_targets(agent)
    except typer.BadParameter as exc:
        base.console.print(str(exc))
        raise typer.Exit(2) from None
    if not targets:
        rows = harness_auth_status(get_llm_config(root))
        installed = [row for row in rows if row["installed"]]
        if json_out:
            base._emit_json({"harnesses": rows, "signed_in": []})
        elif not installed:
            base.console.print(format_harness_status(rows))
        else:
            base.console.print("All installed agents already have a key or CLI login.")
            base.console.print(format_harness_status(rows))
        raise typer.Exit(0 if installed else 2)
    cfg = get_llm_config(root)
    signed_in_kind = normalize_login_agent(agent) if agent else None
    already_signed_in = {
        "claude": ("claude", claude_auth_kind, "Code agent is already signed in"),
        "cursor": ("cursor", cursor_auth_kind, "Editor agent is already signed in"),
    }
    if signed_in_kind in already_signed_in and not force:
        name, auth_kind, message = already_signed_in[signed_in_kind]
        if auth_kind(cfg) == AUTH_CLI_LOGIN:
            if json_out:
                base._emit_json(
                    {
                        "results": [
                            {
                                "agent": name,
                                "ok": True,
                                "installed": True,
                                "status": "logged in",
                                "message": message,
                            }
                        ],
                        "harnesses": harness_auth_status(cfg),
                    }
                )
            else:
                base.console.print(message)
            raise typer.Exit(0)
    results = [run_official_login(name, cfg) for name in targets]
    if json_out:
        base._emit_json({"results": results, "harnesses": harness_auth_status(cfg)})
        if any(not item.get("installed") for item in results):
            raise typer.Exit(2)
        raise typer.Exit(0 if all(item.get("ok") for item in results) else 1)
    code = 0
    for item in results:
        if not item.get("installed"):
            base.console.print(f"{item.get('agent')}: not installed.")
            base.console.print(str(item.get("install") or ""))
            code = max(code, 2)
            continue
        base.console.print(str(item.get("message") or ""))
        if not item.get("ok"):
            code = max(code, 1)
    base.console.print(format_harness_status(harness_auth_status(cfg)))
    raise typer.Exit(code)


def doctor(
    json_out: bool = typer.Option(False, "--json", help="Machine JSON"),
) -> None:
    """Show whether agents are installed and signed in."""
    _print_agent_status(json_out=json_out)


def ingest(
    skill: Path = typer.Argument(..., help="Path to a skill folder containing SKILL.md"),
) -> None:
    """Validate a skill folder against the agentskills spec."""
    try:
        loaded = ingest_skill(skill)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    base.console.print(f"OK  {loaded.name}")
    base.console.print(loaded.description)
    if loaded.warning:
        base.console.print(f"Warning: {loaded.warning}")
