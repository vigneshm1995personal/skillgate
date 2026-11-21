#!/usr/bin/env python3
# ruff: noqa: E501
"""Post-process split cli package."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "src/skillgate_ai/cli"
ORIG = ROOT / "src/skillgate_ai/cli.py"

CMD_HEADER = '''"""CLI commands."""

from __future__ import annotations

from pathlib import Path

import typer

import skillgate_ai.cli.base as base
from skillgate_ai.cli.base import (
    _HARNESS_HELP,
    _KEY_ENV_HELP,
    _SANDBOX_HELP,
    _VERBOSE_HELP,
    _bind_key_env,
    _boot,
    _emit_json,
    _read_omitted_key,
    _resolve_pack_arg,
    app,
    case_app,
    checks_app,
    console,
    examples_app,
    judge_app,
    judge_provider_app,
    keys_app,
)

'''

MODULE_EXTRAS: dict[str, str] = {
    "cmd_gate": """
import os
import sys
from typing import NoReturn

from skillgate_ai.api_payloads import scrub_browser_payload
from skillgate_ai.errors import SkillGateError, timeout_harness_error
from skillgate_ai.gate import run_check
from skillgate_ai.paths import project_root, resolve_user_path
from skillgate_ai.report import format_cli, format_github, report_to_dict
""",
}

ADD_TYPER = """
app.add_typer(keys_app, name="keys")
app.add_typer(examples_app, name="examples")
app.add_typer(judge_app, name="judge")
judge_app.add_typer(judge_provider_app, name="provider")
app.add_typer(checks_app, name="checks")
app.add_typer(case_app, name="case")
"""


def strip_decorator_lines(text: str) -> str:
    lines = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("@app.") or s.startswith("@keys_app.") or s.startswith("@examples_app."):
            continue
        if s.startswith("@judge_app.") or s.startswith("@checks_app.") or s.startswith("@case_app."):
            continue
        if s.startswith("@judge_provider_app."):
            continue
        lines.append(line)
    return "\n".join(lines) + "\n"


def qualify_base(text: str) -> str:
    for sym in (
        "_boot",
        "_emit_json",
        "_bind_key_env",
        "_read_omitted_key",
        "_resolve_pack_arg",
        "console",
        "_HARNESS_HELP",
        "_SANDBOX_HELP",
        "_KEY_ENV_HELP",
        "_VERBOSE_HELP",
        "_stdin_is_tty",
    ):
        text = re.sub(rf"(?<![.\w]){sym}(?=\()", f"base.{sym}", text)
        text = re.sub(rf"(?<![.\w]){sym}\.", f"base.{sym}.", text)
        text = re.sub(rf"(?<![.\w]){sym}(?=\s*[,)])", f"base.{sym}", text)
    return text


def extract_body(path: Path) -> str:
    raw = path.read_text(encoding="utf-8")
    # first top-level def
    m = re.search(r"^(def |@)", raw, re.M)
    if not m:
        return raw
    body = raw[m.start() :]
    body = strip_decorator_lines(body)
    return qualify_base(body)


def process_cmd_modules() -> None:
    for path in sorted(CLI.glob("cmd_*.py")):
        body = extract_body(path)
        extra = MODULE_EXTRAS.get(path.stem, "")
        path.write_text(CMD_HEADER + extra + body, encoding="utf-8")


def process_base() -> None:
    path = CLI / "base.py"
    raw = path.read_text(encoding="utf-8")
    # keep only through first duplicate - clean double future
    raw = raw.replace("from __future__ import annotations\n\nfrom __future__ import annotations\n", "from __future__ import annotations\n\n")
    # remove command decorators except @app.callback on _main
    lines = []
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("@app.command"):
            continue
        lines.append(line)
    text = "\n".join(lines) + "\n"
    if "app.add_typer(keys_app" not in text:
        anchor = 'help="Add checks to evals/cases.yaml.",\n)\n'
        pos = text.find(anchor)
        if pos < 0:
            pos = text.find("case_app = typer.Typer")
            pos = text.find("\n", pos) + 1
        text = text[:pos] + "\n" + ADD_TYPER + text[pos:]
    path.write_text(text, encoding="utf-8")


def write_tree() -> None:
    content = '''"""Register Typer commands in a fixed order (CLI surface contract)."""

from __future__ import annotations

from skillgate_ai.cli.base import (
    _KEY_ENV_HELP,
    app,
    case_app,
    checks_app,
    examples_app,
    judge_app,
    judge_provider_app,
    keys_app,
)
from skillgate_ai.cli.cmd_agents import doctor, ingest, login, version
from skillgate_ai.cli.cmd_deploy import connect, deploy, helper, list_assets, sync
from skillgate_ai.cli.cmd_gate import check_pack, run_suite
from skillgate_ai.cli.cmd_judge import (
    case_add_cmd,
    checks_show_cmd,
    judge_add_question_cmd,
    judge_provider_set,
    judge_provider_show,
    judge_provider_test,
    judge_reset,
    judge_show,
    judge_test,
)
from skillgate_ai.cli.cmd_keys import keys_clear, keys_list, keys_set
from skillgate_ai.cli.cmd_scaffold import (
    example_cmd,
    examples_install_cmd,
    examples_list_cmd,
    init_cmd,
    new_cmd,
)
from skillgate_ai.cli.cmd_ui import ui_cmd
from skillgate_ai.cli.pack_commands import register_pack_commands
from skillgate_ai.cli_compare import register_compare_commands


def register_all() -> None:
    app.command()(version)
    app.command()(login)
    app.command()(doctor)
    app.command()(ingest)
    app.command("check")(check_pack)
    app.command("run")(run_suite)
    app.command()(deploy)
    app.command()(sync)
    app.command()(connect)
    app.command()(helper)
    app.command("list")(list_assets)
    keys_app.command("set")(keys_set)
    keys_app.command("clear")(keys_clear)
    keys_app.command("list")(keys_list)
    app.command("init")(init_cmd)
    app.command("new")(new_cmd)
    app.command("example")(example_cmd)
    examples_app.command("list")(examples_list_cmd)
    examples_app.command("install")(examples_install_cmd)
    checks_app.command("show")(checks_show_cmd)
    judge_app.command("show")(judge_show)
    judge_app.command("reset")(judge_reset)
    judge_app.command("add-question")(judge_add_question_cmd)
    case_app.command("add")(case_add_cmd)
    judge_provider_app.command("show")(judge_provider_show)
    judge_provider_app.command("set")(judge_provider_set)
    judge_app.command("test")(judge_test)
    judge_provider_app.command("test")(judge_provider_test)
    app.command()(ui_cmd)
    register_pack_commands(app, case_app, judge_app)
    register_compare_commands(app, key_env_help=_KEY_ENV_HELP)
'''
    (CLI / "tree.py").write_text(content, encoding="utf-8")


def write_init() -> None:
    rows: list[tuple[str, str]] = [
        ("base", "app"), ("base", "console"), ("base", "_emit_json"), ("base", "_boot"),
        ("base", "_version_callback"), ("base", "_main"), ("base", "_HARNESS_HELP"),
        ("base", "_SANDBOX_HELP"), ("base", "_KEY_ENV_HELP"), ("base", "_VERBOSE_HELP"),
        ("base", "_parse_targets"), ("base", "_bind_key_env"), ("base", "_stdin_is_tty"),
        ("base", "_read_omitted_key"), ("base", "_resolve_pack_arg"), ("base", "keys_app"),
        ("base", "examples_app"), ("base", "judge_app"), ("base", "judge_provider_app"),
        ("base", "checks_app"), ("base", "case_app"),
        ("cmd_agents", "version"), ("cmd_agents", "_print_agent_status"), ("cmd_agents", "_login_targets"),
        ("cmd_agents", "login"), ("cmd_agents", "doctor"), ("cmd_agents", "ingest"),
        ("cmd_gate", "_present_check"), ("cmd_gate", "_verbose_scoring_lines"), ("cmd_gate", "_run_gate"),
        ("cmd_gate", "check_pack"), ("cmd_gate", "run_suite"),
        ("cmd_deploy", "deploy"), ("cmd_deploy", "sync"), ("cmd_deploy", "connect"),
        ("cmd_deploy", "helper"), ("cmd_deploy", "list_assets"),
        ("cmd_keys", "keys_set"), ("cmd_keys", "keys_clear"), ("cmd_keys", "keys_list"),
        ("cmd_scaffold", "init_cmd"), ("cmd_scaffold", "new_cmd"), ("cmd_scaffold", "example_cmd"),
        ("cmd_scaffold", "examples_list_cmd"), ("cmd_scaffold", "examples_install_cmd"),
        ("cmd_judge", "checks_show_cmd"), ("cmd_judge", "judge_show"), ("cmd_judge", "judge_reset"),
        ("cmd_judge", "judge_add_question_cmd"), ("cmd_judge", "case_add_cmd"),
        ("cmd_judge", "judge_provider_show"), ("cmd_judge", "judge_provider_set"),
        ("cmd_judge", "_run_judge_test"), ("cmd_judge", "judge_test"), ("cmd_judge", "judge_provider_test"),
        ("cmd_ui", "ui_cmd"),
    ]
    lines = [
        '"""CLI: skillgate / skillgate-ai. Human output first; JSON opt-in."""\n\n',
        "from __future__ import annotations\n\n",
    ]
    for mod, name in rows:
        lines.append(f"from skillgate_ai.cli.{mod} import {name} as {name}\n")
    lines.append(
        "from skillgate_ai.cli.pack_commands import register_pack_commands as register_pack_commands\n"
    )
    lines.append(
        "from skillgate_ai.cli_compare import register_compare_commands as register_compare_commands\n"
    )
    lines.append("\nfrom skillgate_ai.cli.tree import register_all\n\nregister_all()\n")
    (CLI / "__init__.py").write_text("".join(lines), encoding="utf-8")
    (CLI / "__main__.py").write_text(
        '"""Module entry for python -m skillgate_ai.cli."""\n\nfrom skillgate_ai.cli import app\n\napp()\n',
        encoding="utf-8",
    )


def main() -> None:
    process_base()
    process_cmd_modules()
    write_tree()
    write_init()
    ORIG.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
