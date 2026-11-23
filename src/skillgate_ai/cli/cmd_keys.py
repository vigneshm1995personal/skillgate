"""CLI commands."""

from __future__ import annotations

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.errors import SkillGateError


def keys_set(
    name: str = typer.Argument(
        ...,
        help=(
            "CURSOR_API_KEY | CODEX_API_KEY | OPENAI_API_KEY | "
            "JEV_API_KEY | CLOUDFLARE_API_TOKEN | CUSTOM_DECISION_API_KEY | "
            "AI Gateway key | …"
        ),
    ),
    value: str | None = typer.Argument(
        None,
        help="The secret. Omit to paste hidden (TTY) or read stdin.",
    ),
) -> None:
    """Write a key into `.skillgate/keys` (mode 0600).

    Names include CURSOR_API_KEY, CODEX_API_KEY, OPENAI_API_KEY, JEV_API_KEY,
    CLOUDFLARE_API_TOKEN, CUSTOM_DECISION_API_KEY, and AI Gateway key
    (AI_GATEWAY_API_KEY).
    """
    from skillgate_ai.keys import public_key_name, set_vault_key

    root = base._boot()
    secret = value
    if secret is None:
        secret = (base._read_omitted_key() or "").strip()
    if not secret:
        base.console.print("Pass a key value, or paste it when prompted.")
        raise typer.Exit(2)
    try:
        set_vault_key(root, name, secret)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    base.console.print(f"Saved {public_key_name(name)} in Settings (`.skillgate/keys`).")


def keys_clear(
    name: str = typer.Argument(..., help="Key name to remove"),
) -> None:
    """Remove a key from `.skillgate/keys`."""
    from skillgate_ai.keys import clear_vault_key, internal_key_name, public_key_name, read_vault

    root = base._boot()
    try:
        key = internal_key_name(name)
        if key not in read_vault(root):
            base.console.print(f"No {public_key_name(name)} in Settings.")
            raise typer.Exit(1)
        clear_vault_key(root, name)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    base.console.print(f"Cleared {public_key_name(name)}.")


def keys_list() -> None:
    """Show which keys are set. Never prints values."""
    from skillgate_ai.keys import key_presence

    root = base._boot()
    presence = key_presence(root)
    found = False
    from skillgate_ai.keys import public_key_name

    for name, meta in presence.items():
        if not meta["set"]:
            continue
        found = True
        if meta["from_vault"]:
            source = "Settings"
        elif meta.get("from_home"):
            source = "~/.skillgate/keys"
        else:
            source = "SKILLGATE_* / --key-env"
        base.console.print(f"{public_key_name(name)}  ({source})")
    if not found:
        base.console.print("No keys set. Use `skillgate keys set` or Settings in `skillgate ui`.")
