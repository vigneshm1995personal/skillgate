"""Pack-local file I/O after path containment checks."""

from __future__ import annotations

import os
from pathlib import Path

from skillgate_ai.paths import PathTraversalError, pack_file_at, pack_path_string


def read_pack_text(root: str | Path, rel: str, *, encoding: str = "utf-8") -> str:
    with open(pack_path_string(root, rel), encoding=encoding) as handle:
        return handle.read()


def read_pack_bytes(root: str | Path, rel: str) -> bytes:
    with open(pack_path_string(root, rel), "rb") as handle:
        return handle.read()


def write_pack_text(root: str | Path, rel: str, text: str, *, encoding: str = "utf-8") -> Path:
    target_path = pack_path_string(root, rel)
    parent = os.path.dirname(target_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target_path, "w", encoding=encoding) as handle:
        handle.write(text)
    return pack_file_at(root, rel)


def write_pack_bytes(root: str | Path, rel: str, data: bytes) -> Path:
    target_path = pack_path_string(root, rel)
    parent = os.path.dirname(target_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target_path, "wb") as handle:
        handle.write(data)
    return pack_file_at(root, rel)


def append_pack_line(
    root: str | Path, rel: str, line: str, *, encoding: str = "utf-8"
) -> Path | None:
    try:
        target_path = pack_path_string(root, rel)
    except PathTraversalError:
        return None
    parent = os.path.dirname(target_path)
    try:
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(target_path, "a", encoding=encoding) as handle:
            handle.write(line)
    except OSError:
        return None
    return pack_file_at(root, rel)


def read_pack_lines(root: str | Path, rel: str, *, encoding: str = "utf-8") -> list[str]:
    try:
        target_path = pack_path_string(root, rel)
    except PathTraversalError:
        return []
    if not os.path.isfile(target_path):
        return []
    with open(target_path, encoding=encoding) as handle:
        return handle.read().splitlines()


def is_pack_file(root: str | Path, rel: str) -> bool:
    try:
        target_path = pack_path_string(root, rel)
    except PathTraversalError:
        return False
    return os.path.isfile(target_path)


def is_pack_dir(root: str | Path, rel: str) -> bool:
    try:
        target_path = pack_path_string(root, rel)
    except PathTraversalError:
        return False
    return os.path.isdir(target_path)


def pack_entry_at(root: str | Path, rel: str) -> Path:
    return pack_file_at(root, rel)


def glob_pack_files(root: str | Path, rel_dir: str, pattern: str) -> list[Path]:
    import fnmatch

    parts = [piece for piece in rel_dir.replace("\\", "/").split("/") if piece]
    dir_rel = "/".join(parts)
    try:
        base_str = pack_path_string(root, dir_rel) if dir_rel else os.path.realpath(
            os.path.expanduser(str(root))
        )
    except PathTraversalError:
        return []
    if not os.path.isdir(base_str):
        return []
    out: list[Path] = []
    for name in sorted(os.listdir(base_str)):
        if not fnmatch.fnmatch(name, pattern):
            continue
        child_rel = f"{dir_rel}/{name}" if dir_rel else name
        try:
            if not os.path.isfile(pack_path_string(root, child_rel)):
                continue
            out.append(pack_file_at(root, child_rel))
        except PathTraversalError:
            continue
    return out
