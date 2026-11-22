"""CLI commands for compare runs (models + versions)."""

from __future__ import annotations

import typer

from skillgate_ai.cli.compare_jobs import (
    register_compare_cancel,
    register_compare_list,
    register_compare_show,
)
from skillgate_ai.cli.compare_run import register_compare_models, register_compare_versions


def register_compare_commands(app: typer.Typer, *, key_env_help: str) -> None:
    compare_app = typer.Typer(
        add_completion=False,
        no_args_is_help=True,
        help="Side-by-side compare on one Dataset (models or versions).",
    )
    app.add_typer(compare_app, name="compare")
    register_compare_models(compare_app, key_env_help=key_env_help)
    register_compare_versions(compare_app, key_env_help=key_env_help)
    register_compare_show(compare_app)
    register_compare_cancel(compare_app)
    register_compare_list(compare_app)
