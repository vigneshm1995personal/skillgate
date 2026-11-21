#!/usr/bin/env python3
"""Split a flat skillgate_ai module into a package by symbol table."""

from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

BUILTINS = set(dir(__builtins__)) if isinstance(__builtins__, dict) else set(dir(__builtins__))


def _module_header(source: str, tree: ast.Module) -> str:
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


def _collect_top_symbols(source: str, tree: ast.Module) -> dict[str, str]:
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
                dec_lines: list[str] = []
                for dec in node.decorator_list:
                    dseg = ast.get_source_segment(source, dec)
                    if dseg:
                        dec_lines.append(f"@{dseg}")
                if dec_lines:
                    seg = "\n".join(dec_lines) + "\n" + seg
            if seg:
                out[name] = seg
    return out


def _symbol_to_submodule(mapping: dict[str, list[str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for mod, names in mapping.items():
        for n in names:
            if n != "__all__":
                out[n] = mod
    return out


def _names_used_in_code(code: str) -> set[str]:
    tree = ast.parse(code)
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            used.add(node.id)
    return used


def _fix_cross_imports(
    body: str,
    *,
    pkg: str,
    submod: str,
    local_names: set[str],
    sym_map: dict[str, str],
) -> str:
    used = _names_used_in_code(body)
    need: dict[str, list[str]] = {}
    for n in sorted(used):
        if n in local_names or n in BUILTINS:
            continue
        target = sym_map.get(n)
        if target is None or target == submod:
            continue
        need.setdefault(target, []).append(n)
    if not need:
        return body
    imports = ""
    for mod in sorted(need):
        names = need[mod]
        if len(names) == 1:
            imports += f"from {pkg}.{mod} import {names[0]}\n"
        else:
            joined = ", ".join(names)
            imports += f"from {pkg}.{mod} import {joined}\n"
    return imports + "\n" + body


def split_package(
    src: Path,
    dest: Path,
    pkg_import: str,
    mapping: dict[str, list[str]],
    *,
    init_doc_extra: str = "",
    pass_through: str | None = None,
    extra_init: str | None = None,
) -> None:
    source = src.read_text(encoding="utf-8")
    tree = ast.parse(source)
    header = _module_header(source, tree)
    symbols = _collect_top_symbols(source, tree)
    sym_map = _symbol_to_submodule(mapping)

    dest.mkdir(parents=True, exist_ok=True)
    all_reexport: list[str] = []

    for submod, names in mapping.items():
        local_names = set(names)
        chunks: list[str] = []
        for n in names:
            if n == "__all__":
                continue
            if n not in symbols:
                raise SystemExit(f"missing symbol {n} in {src}")
            chunks.append(symbols[n] + "\n\n")
            all_reexport.append(n)
        body = "".join(chunks)
        body = _fix_cross_imports(
            body,
            pkg=pkg_import,
            submod=submod,
            local_names=local_names,
            sym_map=sym_map,
        )
        (dest / f"{submod}.py").write_text(header + body, encoding="utf-8")

    init_parts: list[str] = []
    doc = tree.body[0] if tree.body else None
    if (
        isinstance(doc, ast.Expr)
        and isinstance(doc.value, ast.Constant)
        and isinstance(doc.value.value, str)
    ):
        init_parts.append(f'"""{doc.value.value}"""\n\n')
    else:
        init_parts.append('"""\n"""\n\n')
    if init_doc_extra:
        init_parts[0] = init_parts[0].rstrip('"\n') + "\n" + init_doc_extra + '\n"""\n\n'
    init_parts.append("from __future__ import annotations\n\n")
    if pass_through:
        init_parts.append(pass_through + "\n\n")
    for submod, names in mapping.items():
        for n in names:
            if n == "__all__":
                continue
            init_parts.append(f"from {pkg_import}.{submod} import {n} as {n}\n")
    if extra_init:
        init_parts.append("\n" + extra_init)
    if "__all__" in symbols:
        init_parts.append("\n" + symbols["__all__"] + "\n")
    (dest / "__init__.py").write_text("".join(init_parts), encoding="utf-8")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("src")
    p.add_argument("dest")
    p.add_argument("pkg_import")
    p.add_argument("--map-json", required=True)
    p.add_argument("--pass-through", default="")
    p.add_argument("--delete-src", action="store_true")
    args = p.parse_args()

    mapping = json.loads(args.map_json)
    src = Path(args.src)
    dest = Path(args.dest)
    split_package(
        src,
        dest,
        args.pkg_import,
        mapping,
        pass_through=args.pass_through or None,
    )
    if args.delete_src:
        src.unlink()
    subprocess.check_call(
        [sys.executable, "-m", "ruff", "check", str(dest), "--fix"],
        cwd=src.parent.parent.parent,
    )
    subprocess.check_call(
        [sys.executable, "-m", "ruff", "format", str(dest)],
        cwd=src.parent.parent.parent,
    )


if __name__ == "__main__":
    main()
