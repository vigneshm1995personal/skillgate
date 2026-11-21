#!/usr/bin/env python3
"""Split a flat module into a package by top-level symbol names (move-only)."""

from __future__ import annotations

import argparse
import ast
import textwrap
from pathlib import Path


def _header_lines(tree: ast.Module) -> str:
    lines: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Expr)):
            if isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant):
                break
            if isinstance(node, ast.Expr):
                val = node.value
                if not (isinstance(val, ast.Constant) and isinstance(val.value, str)):
                    break
        else:
            break
        segment = ast.get_source_segment("\n".join(open(tree._source_path).read().splitlines()), node)  # type: ignore[attr-defined]
        if segment:
            lines.append(segment)
    return "\n".join(lines) + "\n\n"


def _collect_nodes(tree: ast.Module, source: str) -> dict[str, ast.stmt]:
    out: dict[str, ast.stmt] = {}
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
            if seg:
                out[name] = seg
    return out


def split_module(
    src: Path,
    dest_pkg: Path,
    mapping: dict[str, list[str]],
    *,
    pass_through_init: str | None = None,
) -> None:
    source = src.read_text(encoding="utf-8")
    tree = ast.parse(source)
    tree._source_path = str(src)  # type: ignore[attr-defined]
    nodes = _collect_nodes(tree, source)

  # module docstring from original
    doc = tree.body[0]
    docstr = ""
    if isinstance(doc, ast.Expr) and isinstance(doc.value, ast.Constant):
        docstr = f'"""{doc.value.value}"""\n\n'

    header = docstr + "from __future__ import annotations\n\n"
    # imports: all import nodes before first def
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            seg = ast.get_source_segment(source, node)
            if seg:
                header += seg + "\n"
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            if docstr and isinstance(node.value.value, str):
                continue
        else:
            break
    header += "\n"

    dest_pkg.mkdir(parents=True, exist_ok=True)
    reexports: list[str] = []

    for mod, names in mapping.items():
        parts = [header]
        missing = [n for n in names if n not in nodes and n != "__all__"]
        if missing:
            raise SystemExit(f"{mod}: missing symbols {missing}")
        for n in names:
            if n == "__all__":
                continue
            if n in nodes:
                parts.append(nodes[n] + "\n\n")
                reexports.append(n)
        (dest_pkg / f"{mod}.py").write_text("".join(parts), encoding="utf-8")

    init_lines = [
        docstr or '"""Skill Gate judge (OpenAI decisions backend)."""\n\n',
        "from __future__ import annotations\n\n",
    ]
    if pass_through_init:
        init_lines.append(pass_through_init + "\n\n")
    for mod, names in mapping.items():
        for n in names:
            if n == "__all__":
                continue
            init_lines.append(f"from skillgate_ai.judge_openai.{mod} import {n} as {n}\n")
    if "__all__" in nodes:
        init_lines.append("\n" + nodes["__all__"] + "\n")
    (dest_pkg / "__init__.py").write_text("".join(init_lines), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("src")
    p.add_argument("dest_pkg")
    p.add_argument("--map", required=True, help="json-like not implemented")
    args = p.parse_args()
    raise SystemExit("use from split_judge_openai.py")


if __name__ == "__main__":
    main()