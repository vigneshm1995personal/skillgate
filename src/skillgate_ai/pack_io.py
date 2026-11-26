"""Pack-local file I/O after path containment checks."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.contained_fs import (
    _split_rel as _split_rel,
)
from skillgate_ai.contained_fs import (
    append_text_line,
    file_size,
    isdir_at,
    isfile_at,
    list_names,
    read_bytes_at,
    read_text,
    write_bytes_at,
    write_text,
)
from skillgate_ai.paths import PathTraversalError, pack_access_root, pack_file_at


def _pack_parts(skill_path: str | Path, rel: str) -> tuple[Path, tuple[str, ...]]:
    anchor, prefix = pack_access_root(skill_path)
    return anchor, (*prefix, *_split_rel(rel))


def read_pack_text(root: str | Path, rel: str, *, encoding: str = "utf-8") -> str:
    anchor, parts = _pack_parts(root, rel)
    return read_text(anchor, *parts, encoding=encoding)


def read_pack_bytes(root: str | Path, rel: str) -> bytes:
    anchor, parts = _pack_parts(root, rel)
    return read_bytes_at(anchor, *parts)


def write_pack_text(root: str | Path, rel: str, text: str, *, encoding: str = "utf-8") -> Path:
    anchor, parts = _pack_parts(root, rel)
    write_text(anchor, *parts, text=text, encoding=encoding)
    return pack_file_at(root, rel)


def write_pack_bytes(root: str | Path, rel: str, data: bytes) -> Path:
    anchor, parts = _pack_parts(root, rel)
    write_bytes_at(anchor, *parts, data=data)
    return pack_file_at(root, rel)


def append_pack_line(
    root: str | Path, rel: str, line: str, *, encoding: str = "utf-8"
) -> Path | None:
    try:
        anchor, parts = _pack_parts(root, rel)
        append_text_line(anchor, *parts, line=line, encoding=encoding)
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
        anchor, parts = _pack_parts(root, rel)
        return isfile_at(anchor, *parts)
    except PathTraversalError:
        return False


def is_pack_dir(root: str | Path, rel: str) -> bool:
    try:
        anchor, parts = _pack_parts(root, rel)
        return isdir_at(anchor, *parts)
    except PathTraversalError:
        return False


def pack_entry_at(root: str | Path, rel: str) -> Path:
    return pack_file_at(root, rel)


def pack_file_size(root: str | Path, rel: str) -> int:
    anchor, parts = _pack_parts(root, rel)
    return file_size(anchor, *parts)


def glob_pack_files(root: str | Path, rel_dir: str, pattern: str) -> list[Path]:
    import fnmatch

    try:
        anchor, pack_prefix = pack_access_root(root)
        dir_parts = (*pack_prefix, *_split_rel(rel_dir))
        names = list_names(anchor, *dir_parts)
    except PathTraversalError:
        return []
    out: list[Path] = []
    dir_slash = rel_dir.replace("\\", "/").strip().rstrip("/")
    for name in names:
        if not fnmatch.fnmatch(name, pattern):
            continue
        pack_rel = f"{dir_slash}/{name}" if dir_slash else name
        try:
            out.append(pack_file_at(root, pack_rel))
        except PathTraversalError:
            continue
    return out
