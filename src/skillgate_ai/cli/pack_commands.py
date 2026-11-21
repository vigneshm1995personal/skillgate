"""Register pack-related CLI commands (import order = CLI surface)."""

from __future__ import annotations

import typer

from skillgate_ai.cli.pack_case import (
    register_case_bind,
    register_case_edit,
    register_case_import,
    register_case_list,
    register_case_remove,
)
from skillgate_ai.cli.pack_history import (
    register_history_app,
    register_history_callback,
    register_history_show,
)
from skillgate_ai.cli.pack_judge import register_judge_remove_question, register_judge_set_question
from skillgate_ai.cli.pack_skill import (
    register_import_command,
    register_skill_app,
    register_skill_paste,
    register_skill_write,
)


def register_pack_commands(app: typer.Typer, case_app: typer.Typer, judge_app: typer.Typer) -> None:
    skill_app = register_skill_app(app)
    register_import_command(app)
    register_skill_write(skill_app)
    register_skill_paste(skill_app)
    history_app = register_history_app(app)
    register_history_callback(history_app)
    register_history_show(history_app)
    register_case_list(case_app)
    register_case_remove(case_app)
    register_case_edit(case_app)
    register_case_import(case_app)
    register_case_bind(case_app)
    register_judge_remove_question(judge_app)
    register_judge_set_question(judge_app)
