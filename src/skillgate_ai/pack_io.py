"""Pack-local file I/O after path containment checks."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.contained_fs import (
    append_text_line,
    glob_files,
    isdir_at,
    isfile_at,
    read_bytes_at,
    read_text,
    write_bytes_at,
    write_text,
)
from skillgate_ai.paths import PathTraversalError, pack_file_at


def _parts(rel: str) -> tuple[str, ...]:
    from skillgate_ai.contained_fs import _split_rel

    return _split_rel(rel)


def read_pack_text(root: str | Path, rel: str, *, encoding: str = "utf-8") -> str:
    return read_text(root, *_parts(rel), encoding=encoding)


def read_pack_bytes(root: str | Path, rel: str) -> bytes:
    return read_bytes_at(root, *_parts(rel))


def write_pack_text(root: str | Path, rel: str, text: str, *, encoding: str = "utf-8") -> Path:
    parts = _parts(rel)
    write_text(root, *parts, text=text, encoding=encoding)
    return pack_file_at(root, rel)


def write_pack_bytes(root: str | Path, rel: str, data: bytes) -> Path:
    write_bytes_at(root, *_parts(rel), data=data)
    return pack_file_at(root, rel)


def append_pack_line(
    root: str | Path, rel: str, line: str, *, encoding: str = "utf-8"
) -> Path | None:
    try:
        append_text_line(root, *_parts(rel), line=line, encoding=encoding)
    except PathTraversalError:
        return None
    except OSError:
        return None
    return pack_file_at(root, rel)


def read_pack_lines(root: str | Path, rel: str, *, encoding: str = "utf-8") -> list[str]:
    try:
        text = read_pack_text(root, rel, encoding=encoding)
    except (PathTraversalError, OSError):
        return []
    if not is_pack_file(root, rel):
        return []
    return text.splitlines()


def is_pack_file(root: str | Path, rel: str) -> bool:
    try:
        return isfile_at(root, *_parts(rel))
    except PathTraversalError:
        return False


def is_pack_dir(root: str | Path, rel: str) -> bool:
    try:
        return isdir_at(root, *_parts(rel))
    except PathTraversalError:
        return False


def pack_entry_at(root: str | Path, rel: str) -> Path:
    return pack_file_at(root, rel)


def glob_pack_files(root: str | Path, rel_dir: str, pattern: str) -> list[Path]:
    try:
        rels = glob_files(root, rel_dir, pattern)
    except PathTraversalError:
        return []
    out: list[Path] = []
    for rel in rels:
        try:
            out.append(pack_file_at(root, rel))
        except PathTraversalError:
            continue
    return out
