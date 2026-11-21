#!/usr/bin/env python3
from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path("src/skillgate_ai/cli_pack.py")
CLI = Path("src/skillgate_ai/cli")
source = SRC.read_text(encoding="utf-8")
lines = source.splitlines(keepends=True)
tree = ast.parse(source)


def segment(node: ast.AST) -> str:
    return "".join(lines[node.lineno - 1 : node.end_lineno])


def dedent_decorators(body: str) -> str:
    out: list[str] = []
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("@"):
            continue
        out.append(line)
    return "\n".join(out).strip() + "\n"


def lazy_cli_imports(body: str) -> str:
  body = body.replace("_resolve_pack_arg", "_cli._resolve_pack_arg")
  body = body.replace("_boot()", "_cli._boot()")
  body = body.replace("console.", "_cli.console.")
  body = re.sub(
      r'from skillgate_ai\.cli import _emit_json',
      'from skillgate_ai.cli import _emit_json',
      body,
  )
  return body


reg = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "register_pack_commands")
nested = {n.name: dedent_decorators(segment(n)) for n in reg.body if isinstance(n, ast.FunctionDef)}

flag_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_output_optional_flag")

LAZY = "    from skillgate_ai import cli as _cli\n\n"

pack_case = '''"""Pack CLI: case commands."""

from __future__ import annotations

from pathlib import Path

import typer

from skillgate_ai.errors import SkillGateError


'''
pack_case += segment(flag_fn) + "\n\n"


def wrap_register(name: str, inner_name: str, body: str, app_arg: str, cmd: str) -> str:
    body = lazy_cli_imports(body)
    return f'''def {name}({app_arg}: typer.Typer) -> None:
{LAZY}    def {inner_name}(
'''
    # broken - use simpler template

SCRIPT