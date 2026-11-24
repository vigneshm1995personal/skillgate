"""CLI: skillgate / skillgate-ai. Human output first; JSON opt-in."""

from __future__ import annotations

import getpass
import json
import sys
from pathlib import Path

import typer
from rich.console import Console

from skillgate_ai import __version__
from skillgate_ai.config import load_env
from skillgate_ai.errors import SkillGateError
from skillgate_ai.keys import bind_key_env, reset_key_env_bindings
from skillgate_ai.paths import is_skill_pack, project_root, resolve_user_path

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_enable=False,
    pretty_exceptions_show_locals=False,
    help="Skill Gate — evaluate agent skills. Pack on disk + `skillgate check` (exit 0/1).",
)

console = Console(stderr=False)


def _emit_json(payload: object) -> None:
    """Write JSON to stdout with no terminal wrapping. Safe to pipe to json.tool."""
    sys.stdout.write(json.dumps(payload, indent=2, ensure_ascii=True) + "\n")
    sys.stdout.flush()


def _boot() -> Path:
    root = project_root()
    load_env(root)
    return root


def _version_callback(value: bool) -> None:
    if value:
        console.print(__version__)
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Print the CLI version.",
    ),
) -> None:
    """Skill Gate."""
    del version


_HARNESS_HELP = "auto | cursor | cursor-agent | codex | claude"

_SANDBOX_HELP = "local (default)"

_KEY_ENV_HELP = (
    "Use this process env name as a Skill Gate key (repeatable). "
    "CI: set SKILLGATE_OPENAI_API_KEY, or pass --key-env OPENAI_API_KEY."
)

_VERBOSE_HELP = "Print the sanitized upstream scoring reason when the test fails."


def _parse_targets(*values: str | None, default: str = "cursor") -> list[str]:
    found: list[str] = []
    for raw in values:
        if not raw:
            continue
        for part in raw.split(","):
            name = part.strip().lower()
            if name and name not in found:
                found.append(name)
    if found:
        return found
    return [part.strip() for part in default.split(",") if part.strip()]


def _bind_key_env(key_env: list[str] | None) -> None:
    reset_key_env_bindings()
    bind_key_env(key_env)


def _stdin_is_tty() -> bool:
    try:
        return sys.stdin.isatty()
    except (AttributeError, OSError, ValueError):
        return False


def _read_omitted_key() -> str:
    if _stdin_is_tty():
        return getpass.getpass("Value (hidden): ")
    return sys.stdin.read()


def _resolve_pack_arg(
    pack: Path | None, *, default_pdf: bool = True, prefer_cwd_pack: bool = False
) -> Path:
    from skillgate_ai.paths import nearest_skill_pack

    root = _boot()
    if pack is not None:
        dest = resolve_user_path(pack, root)
    elif prefer_cwd_pack and (found := nearest_skill_pack()) is not None:
        dest = found
    elif is_skill_pack(root):
        dest = root
    elif default_pdf:
        pdf = root / "skills" / "pdf"
        if is_skill_pack(pdf):
            dest = pdf
        else:
            raise SkillGateError(
                "Pass a skill pack (folder with SKILL.md and evals/).",
                exit_code=2,
            )
    else:
        raise SkillGateError(
            "Pass a skill pack (folder with SKILL.md and evals/).",
            exit_code=2,
        )
    if not (dest / "SKILL.md").is_file():
        raise SkillGateError(
            f"Not a skill pack: {dest}",
            hint="Pass a skill folder with SKILL.md and evals/.",
            exit_code=2,
        )
    return dest


keys_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Set keys in this project. Never reads OPENAI_API_KEY from the shell unless --key-env.",
)

examples_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="List and install example skills that ship with a dataset.",
)

judge_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Show extra scoring questions and pick who scores live checks.",
)

judge_provider_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Who scores live checks. A decision model is required.",
)

checks_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Show the judge prompt for a built-in or custom check.",
)

case_app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Add checks to evals/cases.yaml.",
)

app.add_typer(keys_app, name="keys")
app.add_typer(examples_app, name="examples")
app.add_typer(judge_app, name="judge")
judge_app.add_typer(judge_provider_app, name="provider")
app.add_typer(checks_app, name="checks")
app.add_typer(case_app, name="case")
