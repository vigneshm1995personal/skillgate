#!/usr/bin/env python3
"""Split cli.py and cli_pack.py into skillgate_ai.cli package (docs/specs/split-giant-files.md)."""

from __future__ import annotations

import ast
import re
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI_SRC = ROOT / "src/skillgate_ai/cli.py"
PACK_SRC = ROOT / "src/skillgate_ai/cli_pack.py"
DEST = ROOT / "src/skillgate_ai/cli"

CLI_MAP: dict[str, list[str]] = {
    "base": [
        "app",
        "console",
        "_emit_json",
        "_boot",
        "_version_callback",
        "_main",
        "_HARNESS_HELP",
        "_SANDBOX_HELP",
        "_KEY_ENV_HELP",
        "_VERBOSE_HELP",
        "_parse_targets",
        "_bind_key_env",
        "_stdin_is_tty",
        "_read_omitted_key",
        "_resolve_pack_arg",
        "keys_app",
        "examples_app",
        "judge_app",
        "judge_provider_app",
        "checks_app",
        "case_app",
    ],
    "cmd_agents": [
        "version",
        "_print_agent_status",
        "_login_targets",
        "login",
        "doctor",
        "ingest",
    ],
    "cmd_gate": [
        "_present_check",
        "_verbose_scoring_lines",
        "_run_gate",
        "check_pack",
        "run_suite",
    ],
    "cmd_deploy": ["deploy", "sync", "connect", "helper", "list_assets"],
    "cmd_keys": ["keys_set", "keys_clear", "keys_list"],
    "cmd_scaffold": ["init_cmd", "new_cmd", "example_cmd", "examples_list_cmd", "examples_install_cmd"],
    "cmd_judge": [
        "checks_show_cmd",
        "judge_show",
        "judge_reset",
        "judge_add_question_cmd",
        "case_add_cmd",
        "judge_provider_show",
        "judge_provider_set",
        "_run_judge_test",
        "judge_test",
        "judge_provider_test",
    ],
    "cmd_ui": ["ui_cmd"],
}

# (typer_var, kind, name, func, help_var)
TREE_ROWS: list[tuple[str, str, str | None, str, str | None]] = [
    ("app", "command", None, "version", None),
    ("app", "command", None, "login", None),
    ("app", "command", None, "doctor", None),
    ("app", "command", None, "ingest", None),
    ("app", "command", "check", "check_pack", None),
    ("app", "command", "run", "run_suite", None),
    ("app", "command", None, "deploy", None),
    ("app", "command", None, "sync", None),
    ("app", "command", None, "connect", None),
    ("app", "command", None, "helper", None),
    ("app", "command", "list", "list_assets", None),
    ("keys_app", "command", "set", "keys_set", None),
    ("keys_app", "command", "clear", "keys_clear", None),
    ("keys_app", "command", "list", "keys_list", None),
    ("app", "command", "init", "init_cmd", None),
    ("app", "command", "new", "new_cmd", None),
    ("app", "command", "example", "example_cmd", None),
    ("examples_app", "command", "list", "examples_list_cmd", None),
    ("examples_app", "command", "install", "examples_install_cmd", None),
    ("checks_app", "command", "show", "checks_show_cmd", None),
    ("judge_app", "command", "show", "judge_show", None),
    ("judge_app", "command", "reset", "judge_reset", None),
    ("judge_app", "command", "add-question", "judge_add_question_cmd", None),
    ("case_app", "command", "add", "case_add_cmd", None),
    ("judge_provider_app", "command", "show", "judge_provider_show", None),
    ("judge_provider_app", "command", "set", "judge_provider_set", None),
    ("judge_app", "command", "test", "judge_test", None),
    ("judge_provider_app", "command", "test", "judge_provider_test", None),
    ("app", "command", None, "ui_cmd", None),
]

ADD_TYPER = [
    ('app.add_typer(keys_app, name="keys")',),
    ('app.add_typer(examples_app, name="examples")',),
    ('app.add_typer(judge_app, name="judge")',),
    ("judge_app.add_typer(judge_provider_app, name=\"provider\")",),
    ('app.add_typer(checks_app, name="checks")',),
    ('app.add_typer(case_app, name="case")',),
]


def _header(source: str, tree: ast.Module) -> str:
    doc = ""
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(tree.body[0].value, ast.Constant)
        and isinstance(tree.body[0].value.value, str)
    ):
        doc = ast.get_source_segment(source, tree.body[0]) + "\n\n"
    lines = [doc, "from __future__ import annotations\n\n"]
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            lines.append(ast.get_source_segment(source, node) + "\n")
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str) and doc:
                continue
        else:
            break
    lines.append("\n")
    return "".join(lines)


def _collect(source: str, tree: ast.Module) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in tree.body:
        name = None
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    name = t.id
                    break
        if name:
            seg = ast.get_source_segment(source, node)
            if seg and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                dec_lines = []
                for dec in node.decorator_list:
                    dseg = ast.get_source_segment(source, dec)
                    if dseg:
                        dec_lines.append(f"@{dseg}")
                if dec_lines and name != "_main":
                    seg = "\n".join(dec_lines) + "\n" + seg
            if seg:
                out[name] = seg
    return out


def _strip_decorators(body: str) -> str:
    lines = body.splitlines()
    while lines and lines[0].startswith("@"):
        lines.pop(0)
    return "\n".join(lines) + ("\n" if body.endswith("\n") else "")


def _split_cli_py() -> None:
    source = CLI_SRC.read_text(encoding="utf-8")
    tree = ast.parse(source)
    header = _header(source, tree)
    symbols = _collect(source, tree)
    DEST.mkdir(parents=True, exist_ok=True)

    for mod, names in CLI_MAP.items():
        chunks = []
        for n in names:
            if n not in symbols:
                raise SystemExit(f"missing {n} in cli.py")
            body = symbols[n]
            if mod != "base" or n != "_main":
                body = _strip_decorators(body)
            if mod == "cmd_agents" and n == "_login_targets":
                body = body.replace("_stdin_is_tty()", "base._stdin_is_tty()")
            chunks.append(body + "\n\n")
        imports = header
        if mod != "base":
            imports += "from skillgate_ai.cli import base\n"
            imports = imports.replace(
                "from skillgate_ai.cli import base\n",
                "from skillgate_ai.cli.base import (\n"
                "    _boot,\n"
                "    _emit_json,\n"
                "    _bind_key_env,\n"
                "    _read_omitted_key,\n"
                "    _resolve_pack_arg,\n"
                "    _HARNESS_HELP,\n"
                "    _SANDBOX_HELP,\n"
                "    _KEY_ENV_HELP,\n"
                "    _VERBOSE_HELP,\n"
                "    app,\n"
                "    console,\n"
                ")\n",
            )
            text = chunks[0]
            for c in chunks:
                text = text  # noqa
            module_body = "".join(chunks)
            module_body = re.sub(
                r"\b(_boot|_emit_json|_bind_key_env|_read_omitted_key|_resolve_pack_arg|console|"
                r"_HARNESS_HELP|_SANDBOX_HELP|_KEY_ENV_HELP|_VERBOSE_HELP)\b",
                lambda m: f"base.{m.group(1)}"
                if m.group(1) in {"_stdin_is_tty"}
                else (f"base.{m.group(1)}" if m.group(1) != "console" else "base.console"),
                module_body,
            )
            # simpler: replace common names
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
            ):
                module_body = re.sub(rf"(?<![.\w]){sym}(?=\()", f"base.{sym}", module_body)
                module_body = re.sub(rf"(?<![.\w]){sym}(?=\.)", f"base.{sym}", module_body)
                module_body = re.sub(rf"(?<![.\w]){sym}(?=\s|$)", f"base.{sym}", module_body)
            (DEST / f"{mod}.py").write_text(imports + module_body, encoding="utf-8")
        else:
            extra = "\n".join(t[0] for t in ADD_TYPER) + "\n\n"
            (DEST / f"{mod}.py").write_text(imports + extra + "".join(chunks), encoding="utf-8")

    _split_run_gate()
    _write_tree()
    _write_main_init()
    CLI_SRC.unlink()


def _split_run_gate() -> None:
    path = DEST / "cmd_gate.py"
    text = path.read_text(encoding="utf-8")
    if "_exit_with_error" in text:
        return
    # Extract helpers from _run_gate manually via regex blocks
    old = text

    helpers = '''

def _exit_with_error(exc: SkillGateError, *, machine: bool) -> None:
    if machine:
        base._emit_json(
            {
                "error": exc.message,
                "hint": exc.hint,
                "exit_code": exc.exit_code,
            }
        )
    else:
        base.console.print(exc.render())
    raise typer.Exit(exc.exit_code) from None


def _tryout_checks(target: Path, case_id: str, *, machine: bool) -> list:
    from skillgate_ai.pack_edit import tryout_checks
    from skillgate_ai.paths import is_skill_pack

    dest = resolve_user_path(target, project_root())
    if not is_skill_pack(dest):
        _exit_with_error(
            SkillGateError(
                f"Not a skill pack: {dest}",
                hint="Pass a skill folder with SKILL.md and evals/.",
                exit_code=2,
            ),
            machine=machine,
        )
    try:
        return tryout_checks(dest, case_id)
    except SkillGateError as exc:
        _exit_with_error(exc, machine=machine)
    raise AssertionError("unreachable")


'''

    # Replace _run_gate body sections - read current _run_gate and rebuild
    text = old.replace("def _run_gate(", helpers + "def _run_gate(")
    text = re.sub(
        r'    machine = json_out or summary == "json"\n',
        '    machine = json_out or summary == "json"\n',
        text,
    )
    # fix tryout block
    text = re.sub(
        r"    if case_id:\n        from skillgate_ai.pack_edit import tryout_checks\n"
        r"        from skillgate_ai.paths import is_skill_pack\n\n"
        r"        dest = resolve_user_path\(target, project_root\(\)\)\n"
        r"        if not is_skill_pack\(dest\):\n"
        r"            exc = SkillGateError\([\s\S]*?"
        r"            raise typer\.Exit\(exc\.exit_code\) from None\n"
        r"        try:\n            checks = tryout_checks\(dest, case_id\)\n"
        r"            tryout = True\n        except SkillGateError as exc:[\s\S]*?"
        r"            raise typer\.Exit\(exc\.exit_code\) from None",
        '    if case_id:\n        checks = _tryout_checks(target, case_id, machine=json_out or summary == "json")\n        tryout = True\n',
        text,
        count=1,
    )
    path.write_text(text, encoding="utf-8")


def _write_tree() -> None:
    lines = [
        '"""Register Typer commands in a fixed order (CLI surface contract)."""\n\n',
        "from __future__ import annotations\n\n",
        "from skillgate_ai.cli.base import (\n",
        "    _KEY_ENV_HELP,\n",
        "    app,\n",
        "    case_app,\n",
        "    checks_app,\n",
        "    examples_app,\n",
        "    judge_app,\n",
        "    judge_provider_app,\n",
        "    keys_app,\n",
        ")\n",
        "from skillgate_ai.cli.cmd_agents import doctor, ingest, login, version\n",
        "from skillgate_ai.cli.cmd_deploy import connect, deploy, helper, list_assets, sync\n",
        "from skillgate_ai.cli.cmd_gate import check_pack, run_suite\n",
        "from skillgate_ai.cli.cmd_judge import (\n",
        "    case_add_cmd,\n",
        "    checks_show_cmd,\n",
        "    judge_add_question_cmd,\n",
        "    judge_provider_set,\n",
        "    judge_provider_show,\n",
        "    judge_provider_test,\n",
        "    judge_reset,\n",
        "    judge_show,\n",
        "    judge_test,\n",
        ")\n",
        "from skillgate_ai.cli.cmd_keys import keys_clear, keys_list, keys_set\n",
        "from skillgate_ai.cli.cmd_scaffold import (\n",
        "    example_cmd,\n",
        "    examples_install_cmd,\n",
        "    examples_list_cmd,\n",
        "    init_cmd,\n",
        "    new_cmd,\n",
        ")\n",
        "from skillgate_ai.cli.cmd_ui import ui_cmd\n",
        "from skillgate_ai.cli.pack_commands import register_pack_commands\n",
        "from skillgate_ai.cli_compare import register_compare_commands\n\n\n",
        "def register_all() -> None:\n",
    ]
    for typer_var, kind, name, func, _ in TREE_ROWS:
        if name:
            lines.append(f'    {typer_var}.{kind}("{name}")({func})\n')
        else:
            lines.append(f"    {typer_var}.{kind}()({func})\n")
    lines.append("    register_pack_commands(app, case_app, judge_app)\n")
    lines.append("    register_compare_commands(app, key_env_help=_KEY_ENV_HELP)\n")
    (DEST / "tree.py").write_text("".join(lines), encoding="utf-8")


def _write_main_init() -> None:
    reexports: list[str] = []
    for mod, names in CLI_MAP.items():
        for n in names:
            reexports.append(f"from skillgate_ai.cli.{mod} import {n} as {n}\n")
    reexports.append(
        "from skillgate_ai.cli.pack_commands import register_pack_commands as register_pack_commands\n"
    )
    reexports.append(
        "from skillgate_ai.cli_compare import register_compare_commands as register_compare_commands\n"
    )
    init = (
        '"""CLI: skillgate / skillgate-ai. Human output first; JSON opt-in."""\n\n'
        "from __future__ import annotations\n\n"
        + "".join(reexports)
        + "\nfrom skillgate_ai.cli.tree import register_all\n\nregister_all()\n"
    )
    (DEST / "__init__.py").write_text(init, encoding="utf-8")
    (DEST / "__main__.py").write_text(
        "from skillgate_ai.cli import app\n\napp()\n",
        encoding="utf-8",
    )


def _split_cli_pack() -> None:
    """Move cli_pack.py body into pack_* modules (line-range split from monolithic register)."""
    source = PACK_SRC.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    # Keep _output_optional_flag at top
    pack_case_header = ''.join(lines[:17])
    body = "".join(lines[17:])
    # crude: write entire register_pack_commands to pack_commands then split manually later
    (DEST / "pack_case.py").write_text(
        pack_case_header.replace("from skillgate_ai.errors", "from skillgate_ai.errors")
        + "\n",
        encoding="utf-8",
    )
    (DEST / "pack_commands.py").write_text(
        "from __future__ import annotations\n\nimport typer\n\n" + body,
        encoding="utf-8",
    )
    PACK_SRC.write_text(
        "from skillgate_ai.cli.pack_case import _output_optional_flag as _output_optional_flag\n"
        "from skillgate_ai.cli.pack_commands import register_pack_commands as register_pack_commands\n",
        encoding="utf-8",
    )


def main() -> None:
    _split_cli_py()
    _split_cli_pack()


if __name__ == "__main__":
    main()