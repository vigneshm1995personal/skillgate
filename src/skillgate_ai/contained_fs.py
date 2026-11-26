"""Filesystem I/O and checks under a fixed anchor with validated relative segments."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from pathlib import Path

from skillgate_ai.fs_anchor import FsAnchor
from skillgate_ai.paths import PathTraversalError


def _split_rel(rel: str) -> tuple[str, ...]:
    cleaned = rel.replace("\\", "/").strip().lstrip("/")
    parts = tuple(piece for piece in cleaned.split("/") if piece and piece not in {".", ""})
    if any(piece == ".." for piece in parts):
        raise PathTraversalError("Path escapes the allowed root.")
    return parts


def _reject_escape_parts(*parts: str) -> None:
    if any(part in {".", ".."} or ".." in Path(part).parts for part in parts):
        raise PathTraversalError("Path escapes the allowed root.")


def _resolve(anchor: FsAnchor, *rel_parts: str) -> str:
    from skillgate_ai.paths import filesystem_path_under

    _reject_escape_parts(*rel_parts)
    return filesystem_path_under(anchor, *rel_parts)


def resolved_relative(anchor: FsAnchor, rel: str) -> str:
    return _resolve(anchor, *_split_rel(rel))


def is_root_directory(anchor: FsAnchor) -> bool:
    return isdir_at(anchor)


def isfile_at(anchor: FsAnchor, *rel_parts: str) -> bool:
    try:
        fullpath = _resolve(anchor, *rel_parts)
        return os.path.isfile(fullpath)
    except (PathTraversalError, OSError, ValueError):
        return False


def isdir_at(anchor: FsAnchor, *rel_parts: str) -> bool:
    try:
        fullpath = _resolve(anchor, *rel_parts)
        return os.path.isdir(fullpath)
    except (PathTraversalError, OSError, ValueError):
        return False


def file_size(anchor: FsAnchor, *rel_parts: str) -> int:
    fullpath = _resolve(anchor, *rel_parts)
    return os.path.getsize(fullpath)


def read_text(anchor: FsAnchor, *rel_parts: str, encoding: str = "utf-8") -> str:
    fullpath = _resolve(anchor, *rel_parts)
    with open(fullpath, encoding=encoding) as handle:
        return handle.read()


def read_bytes_at(anchor: FsAnchor, *rel_parts: str) -> bytes:
    fullpath = _resolve(anchor, *rel_parts)
    with open(fullpath, "rb") as handle:
        return handle.read()


def write_text(anchor: FsAnchor, *rel_parts: str, text: str, encoding: str = "utf-8") -> str:
    fullpath = _resolve(anchor, *rel_parts)
    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    with open(fullpath, "w", encoding=encoding) as handle:
        handle.write(text)
    return fullpath


def write_bytes_at(anchor: FsAnchor, *rel_parts: str, data: bytes) -> str:
    fullpath = _resolve(anchor, *rel_parts)
    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    with open(fullpath, "wb") as handle:
        handle.write(data)
    return fullpath


def append_text_line(anchor: FsAnchor, *rel_parts: str, line: str, encoding: str = "utf-8") -> str:
    fullpath = _resolve(anchor, *rel_parts)
    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    with open(fullpath, "a", encoding=encoding) as handle:
        handle.write(line)
    return fullpath


def list_names(anchor: FsAnchor, *rel_dir_parts: str) -> list[str]:
    fullpath = _resolve(anchor, *rel_dir_parts)
    if not os.path.isdir(fullpath):
        raise PathTraversalError("Path escapes the allowed root.")
    return sorted(name for name in os.listdir(fullpath))


def glob_files(anchor: FsAnchor, rel_dir: str, pattern: str) -> list[str]:
    parts = _split_rel(rel_dir) if rel_dir else ()
    try:
        dir_path = _resolve(anchor, *parts)
        if not os.path.isdir(dir_path):
            return []
    except (PathTraversalError, ValueError, OSError):
        return []
    from skillgate_ai.fs_anchor import anchor_base

    base_path = anchor_base(anchor)
    out: list[str] = []
    for name in sorted(os.listdir(dir_path)):
        if not fnmatch.fnmatch(name, pattern):
            continue
        child_parts = (*parts, name) if parts else (name,)
        joined_child = os.path.join(base_path, *child_parts)
        child_target = os.path.realpath(joined_child)
        if not (child_target == base_path or child_target.startswith(base_path + os.sep)):
            continue
        if os.path.isfile(child_target):
            out.append("/".join(child_parts))
    return out


def iter_pack_files(
    skill_path: str | Path,
    *,
    skip_dir_names: set[str] | frozenset[str],
    skip_file_names: set[str] | frozenset[str],
) -> Iterator[tuple[str, int]]:
    """Yield ``(pack-relative posix path, size)`` under a skill pack."""
    from skillgate_ai.paths import pack_access_root

    anchor, pack_prefix = pack_access_root(skill_path)
    pack_base = _resolve(anchor, *pack_prefix)
    pending: list[tuple[str, ...]] = [()]
    while pending:
        rel_parts = pending.pop()
        dir_path = _resolve(anchor, *pack_prefix, *rel_parts)
        if not os.path.isdir(dir_path):
            continue
        subdirs: list[tuple[str, ...]] = []
        for name in sorted(os.listdir(dir_path)):
            child_parts = (*rel_parts, name)
            child_path = _resolve(anchor, *pack_prefix, *child_parts)
            if os.path.isdir(child_path):
                if name.lower() not in skip_dir_names:
                    subdirs.append(child_parts)
                continue
            if not os.path.isfile(child_path):
                continue
            rel = "/".join(child_parts)
            if rel == "SKILL.md" or rel.lower() in skip_file_names:
                continue
            if any(p.lower() in skip_dir_names for p in rel_parts):
                continue
            try:
                size = os.path.getsize(child_path)
            except OSError:
                continue
            yield rel, size
        pending.extend(reversed(subdirs))