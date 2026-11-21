"""CLI: skillgate / skillgate-ai. Human output first; JSON opt-in."""

from __future__ import annotations

from skillgate_ai.cli.base import _HARNESS_HELP as _HARNESS_HELP
from skillgate_ai.cli.base import _KEY_ENV_HELP as _KEY_ENV_HELP
from skillgate_ai.cli.base import _SANDBOX_HELP as _SANDBOX_HELP
from skillgate_ai.cli.base import _VERBOSE_HELP as _VERBOSE_HELP
from skillgate_ai.cli.base import _bind_key_env as _bind_key_env
from skillgate_ai.cli.base import _boot as _boot
from skillgate_ai.cli.base import _emit_json as _emit_json
from skillgate_ai.cli.base import _main as _main
from skillgate_ai.cli.base import _parse_targets as _parse_targets
from skillgate_ai.cli.base import _read_omitted_key as _read_omitted_key
from skillgate_ai.cli.base import _resolve_pack_arg as _resolve_pack_arg
from skillgate_ai.cli.base import _stdin_is_tty as _stdin_is_tty
from skillgate_ai.cli.base import _version_callback as _version_callback
from skillgate_ai.cli.base import app as app
from skillgate_ai.cli.base import case_app as case_app
from skillgate_ai.cli.base import checks_app as checks_app
from skillgate_ai.cli.base import console as console
from skillgate_ai.cli.base import examples_app as examples_app
from skillgate_ai.cli.base import judge_app as judge_app
from skillgate_ai.cli.base import judge_provider_app as judge_provider_app
from skillgate_ai.cli.base import keys_app as keys_app
from skillgate_ai.cli.cmd_agents import _login_targets as _login_targets
from skillgate_ai.cli.cmd_agents import _print_agent_status as _print_agent_status
from skillgate_ai.cli.cmd_agents import doctor as doctor
from skillgate_ai.cli.cmd_agents import ingest as ingest
from skillgate_ai.cli.cmd_agents import login as login
from skillgate_ai.cli.cmd_agents import version as version
from skillgate_ai.cli.cmd_deploy import connect as connect
from skillgate_ai.cli.cmd_deploy import deploy as deploy
from skillgate_ai.cli.cmd_deploy import helper as helper
from skillgate_ai.cli.cmd_deploy import list_assets as list_assets
from skillgate_ai.cli.cmd_deploy import sync as sync
from skillgate_ai.cli.cmd_gate import _present_check as _present_check
from skillgate_ai.cli.cmd_gate import _run_gate as _run_gate
from skillgate_ai.cli.cmd_gate import _verbose_scoring_lines as _verbose_scoring_lines
from skillgate_ai.cli.cmd_gate import check_pack as check_pack
from skillgate_ai.cli.cmd_gate import run_suite as run_suite
from skillgate_ai.cli.cmd_judge import _run_judge_test as _run_judge_test
from skillgate_ai.cli.cmd_judge import case_add_cmd as case_add_cmd
from skillgate_ai.cli.cmd_judge import checks_show_cmd as checks_show_cmd
from skillgate_ai.cli.cmd_judge import judge_add_question_cmd as judge_add_question_cmd
from skillgate_ai.cli.cmd_judge import judge_provider_set as judge_provider_set
from skillgate_ai.cli.cmd_judge import judge_provider_show as judge_provider_show
from skillgate_ai.cli.cmd_judge import judge_provider_test as judge_provider_test
from skillgate_ai.cli.cmd_judge import judge_reset as judge_reset
from skillgate_ai.cli.cmd_judge import judge_show as judge_show
from skillgate_ai.cli.cmd_judge import judge_test as judge_test
from skillgate_ai.cli.cmd_keys import keys_clear as keys_clear
from skillgate_ai.cli.cmd_keys import keys_list as keys_list
from skillgate_ai.cli.cmd_keys import keys_set as keys_set
from skillgate_ai.cli.cmd_scaffold import example_cmd as example_cmd
from skillgate_ai.cli.cmd_scaffold import examples_install_cmd as examples_install_cmd
from skillgate_ai.cli.cmd_scaffold import examples_list_cmd as examples_list_cmd
from skillgate_ai.cli.cmd_scaffold import init_cmd as init_cmd
from skillgate_ai.cli.cmd_scaffold import new_cmd as new_cmd
from skillgate_ai.cli.cmd_ui import ui_cmd as ui_cmd
from skillgate_ai.cli.pack_commands import register_pack_commands as register_pack_commands
from skillgate_ai.cli.tree import register_all
from skillgate_ai.cli_compare import register_compare_commands as register_compare_commands

register_all()
