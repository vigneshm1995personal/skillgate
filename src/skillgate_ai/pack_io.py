"""Pack-local file I/O after path containment checks."""

from __future__ import annotations

import os
from pathlib import Path

from skillgate_ai.paths import PathTraversalError, contained_path, pack_file_at


def read_pack_text(root: str | Path, rel: str, *, encoding: str = "utf-8") -> str:
    target = pack_file_at(root, rel)
    with open(os.fsdecode(target), encoding=encoding) as handle:
        return handle.read()


def read_pack_bytes(root: str | Path, rel: str) -> bytes:
    target = pack_file_at(root, rel)
    with open(os.fsdecode(target), "rb") as handle:
        return handle.read()


def write_pack_text(root: str | Path, rel: str, text: str, *, encoding: str = "utf-8") -> Path:
    target = pack_file_at(root, rel)
    parent = os.path.dirname(os.fsdecode(target))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(os.fsdecode(target), "w", encoding=encoding) as handle:
        handle.write(text)
    return target


def write_pack_bytes(root: str | Path, rel: str, data: bytes) -> Path:
    target = pack_file_at(root, rel)
    parent = os.path.dirname(os.fsdecode(target))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(os.fsdecode(target), "wb") as handle:
        handle.write(data)
    return target


def append_pack_line(
    root: str | Path, rel: str, line: str, *, encoding: str = "utf-8"
) -> Path | None:
    try:
        target = pack_file_at(root, rel)
    except PathTraversalError:
        return None
    parent = os.path.dirname(os.fsdecode(target))
    try:
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(os.fsdecode(target), "a", encoding=encoding) as handle:
            handle.write(line)
    except OSError:
        return None
    return target


def read_pack_lines(root: str | Path, rel: str, *, encoding: str = "utf-8") -> list[str]:
    try:
        target = pack_file_at(root, rel)
    except PathTraversalError:
        return []
    if not is_pack_file(root, rel):
        return []
    with open(os.fsdecode(target), encoding=encoding) as handle:
        return handle.read().splitlines()


def is_pack_file(root: str | Path, rel: str) -> bool:
    try:
        target = pack_file_at(root, rel)
    except PathTraversalError:
        return False
    return os.path.isfile(os.fsdecode(target))


def is_pack_dir(root: str | Path, rel: str) -> bool:
    try:
        target = pack_file_at(root, rel)
    except PathTraversalError:
        return False
    return os.path.isdir(os.fsdecode(target))


def pack_entry_at(root: str | Path, rel: str) -> Path:
    return pack_file_at(root, rel)


def glob_pack_files(root: str | Path, rel_dir: str, pattern: str) -> list[Path]:
    import fnmatch

    base = contained_path(root, *[p for p in rel_dir.split("/") if p])
    base_str = os.fsdecode(base)
    if not os.path.isdir(base_str):
        return []
    out: list[Path] = []
    for name in sorted(os.listdir(base_str)):
        if not fnmatch.fnmatch(name, pattern):
            continue
        try:
            candidate = contained_path(base, name)
        except PathTraversalError:
            continue
        if os.path.isfile(os.fsdecode(candidate)):
            out.append(candidate)
    return out
