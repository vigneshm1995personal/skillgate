"""Register Typer commands in a fixed order (CLI surface contract)."""

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
from skillgate_ai.cli.cmd_case import case_add_cmd
from skillgate_ai.cli.cmd_compare import register_compare_commands
from skillgate_ai.cli.cmd_deploy import connect, deploy, helper, list_assets, sync
from skillgate_ai.cli.cmd_gate import check_pack, run_suite
from skillgate_ai.cli.cmd_judge import (
    checks_show_cmd,
    judge_add_question_cmd,
    judge_reset,
    judge_show,
)
from skillgate_ai.cli.cmd_judge_provider import (
    judge_provider_set,
    judge_provider_show,
    judge_provider_test,
    judge_test,
)
from skillgate_ai.cli.cmd_keys import keys_clear, keys_list, keys_set
from skillgate_ai.cli.cmd_mcp import mcp_cmd
from skillgate_ai.cli.cmd_scaffold import (
    example_cmd,
    examples_install_cmd,
    examples_list_cmd,
    init_cmd,
    new_cmd,
)
from skillgate_ai.cli.cmd_ui import ui_cmd
from skillgate_ai.cli.pack_commands import register_pack_commands


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
    app.command("ui")(ui_cmd)
    app.command("mcp")(mcp_cmd)
    register_pack_commands(app, case_app, judge_app)
    register_compare_commands(app, key_env_help=_KEY_ENV_HELP)
