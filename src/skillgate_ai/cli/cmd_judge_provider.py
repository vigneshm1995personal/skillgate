"""CLI commands."""

from __future__ import annotations

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.errors import SkillGateError


def judge_provider_show() -> None:
    """Who scores live checks."""
    from skillgate_ai.judge_providers.decision import NEEDS_DECISION_MODEL_HINT
    from skillgate_ai.judge_settings import load_judge_settings
    from skillgate_ai.judge_setup import format_provider_selection

    root = base._boot()
    settings = load_judge_settings(root)
    base.console.print(format_provider_selection(settings))
    provider = str(getattr(settings, "provider", "") or "auto").strip().lower() or "auto"
    if provider in {"", "auto", "skip"}:
        base.console.print(NEEDS_DECISION_MODEL_HINT)
        raise typer.Exit(2)


def judge_provider_set(
    provider: str = typer.Argument(
        ..., help="A decision-model endpoint id, or auto to clear the selection"
    ),
    base_url: str | None = typer.Option(None, "--base-url"),
    region: str | None = typer.Option(None, "--region"),
    model: str | None = typer.Option(None, "--model"),
    account_id: str | None = typer.Option(
        None, "--account-id", help="Account id for this decision model"
    ),
    decisions_path: str | None = typer.Option(None, "--decisions-path", hidden=True),
    key_env: list[str] | None = typer.Option(None, "--key-env", help=base._KEY_ENV_HELP),
) -> None:
    """Write `.skillgate/judge`. Stores env var names, never key values."""
    from skillgate_ai.judge_settings import save_judge_settings

    root = base._boot()
    try:
        settings = save_judge_settings(
            root,
            provider=provider,
            region=region,
            model=model,
            base_url=base_url,
            decisions_path=decisions_path,
            key_env=key_env,
            account_id=account_id,
        )
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    from skillgate_ai.judge_setup import format_provider_selection

    base.console.print(format_provider_selection(settings))


def _run_judge_test(key_env: list[str] | None, *, verbose: bool = False) -> None:
    from skillgate_ai.config import get_llm_config
    from skillgate_ai.judge import ping_judge

    root = base._boot()
    base._bind_key_env(key_env)
    try:
        result = ping_judge(get_llm_config(root), verbose=verbose)
    except SkillGateError as exc:
        base.console.print(exc.render())
        raise typer.Exit(exc.exit_code) from None
    base.console.print(str(result.get("message") or ""), soft_wrap=True)
    raise typer.Exit(0 if result.get("ok") else 1)


def judge_test(
    key_env: list[str] | None = typer.Option(None, "--key-env", help=base._KEY_ENV_HELP),
    verbose: bool = typer.Option(False, "--verbose", help=base._VERBOSE_HELP),
) -> None:
    """Test the scoring connection. Never prints the key."""
    _run_judge_test(key_env, verbose=verbose)


def judge_provider_test(
    key_env: list[str] | None = typer.Option(None, "--key-env", help=base._KEY_ENV_HELP),
    verbose: bool = typer.Option(False, "--verbose", help=base._VERBOSE_HELP),
) -> None:
    """Test the scoring connection. Never prints the key."""
    _run_judge_test(key_env, verbose=verbose)
