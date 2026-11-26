"""Filesystem I/O and checks under a trusted root with inline containment."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from pathlib import Path

from skillgate_ai.paths import PathTraversalError


def _root_base(root: str | Path) -> str:
    return os.path.realpath(os.path.expanduser(str(root)))


def _split_rel(rel: str) -> tuple[str, ...]:
    cleaned = rel.replace("\\", "/").strip().lstrip("/")
    parts = tuple(piece for piece in cleaned.split("/") if piece and piece not in {".", ""})
    if any(piece == ".." for piece in parts):
        raise PathTraversalError("Path escapes the allowed root.")
    return parts


def _path_under(base: str, *parts: str) -> str:
    if not parts:
        return base
    if any(part in {".", ".."} or ".." in Path(part).parts for part in parts):
        raise PathTraversalError("Path escapes the allowed root.")
    joined = os.path.join(base, *parts)
    target = os.path.realpath(joined)
    try:
        common = os.path.commonpath([base, target])
    except ValueError as exc:
        raise PathTraversalError("Path escapes the allowed root.") from exc
    if common != base:
        raise PathTraversalError("Path escapes the allowed root.")
    return target


def resolved_path(root: str | Path, *rel_parts: str) -> str:
    """Resolved filesystem path for ``rel_parts`` under ``root``."""
    base = _root_base(root)
    if not rel_parts:
        return base
    return _path_under(base, *rel_parts)


def resolved_relative(root: str | Path, rel: str) -> str:
    return resolved_path(root, *_split_rel(rel))


def is_root_directory(root: str | Path) -> bool:
    """True when ``root`` resolves to an existing directory (no extra path parts)."""
    try:
        target = _root_base(root)
    except OSError:
        return False
    return os.path.isdir(target)


def isfile_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        target = resolved_path(root, *rel_parts)
    except (PathTraversalError, OSError):
        return False
    return os.path.isfile(target)


def isdir_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        target = resolved_path(root, *rel_parts)
    except (PathTraversalError, OSError):
        return False
    return os.path.isdir(target)


def file_size(root: str | Path, *rel_parts: str) -> int:
    target = resolved_path(root, *rel_parts)
    return os.path.getsize(target)


def read_text(root: str | Path, *rel_parts: str, encoding: str = "utf-8") -> str:
    target = resolved_path(root, *rel_parts)
    with open(target, encoding=encoding) as handle:
        return handle.read()


def read_bytes_at(root: str | Path, *rel_parts: str) -> bytes:
    target = resolved_path(root, *rel_parts)
    with open(target, "rb") as handle:
        return handle.read()


def write_text(root: str | Path, *rel_parts: str, text: str, encoding: str = "utf-8") -> str:
    target = resolved_path(root, *rel_parts)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "w", encoding=encoding) as handle:
        handle.write(text)
    return target


def write_bytes_at(root: str | Path, *rel_parts: str, data: bytes) -> str:
    target = resolved_path(root, *rel_parts)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(data)
    return target


def append_text_line(root: str | Path, *rel_parts: str, line: str, encoding: str = "utf-8") -> str:
    target = resolved_path(root, *rel_parts)
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(target, "a", encoding=encoding) as handle:
        handle.write(line)
    return target


def list_names(root: str | Path, *rel_dir_parts: str) -> list[str]:
    target = resolved_path(root, *rel_dir_parts)
    if not os.path.isdir(target):
        return []
    return sorted(os.listdir(target))


def glob_files(root: str | Path, rel_dir: str, pattern: str) -> list[str]:
    """Pack-relative posix paths for files in ``rel_dir`` matching ``pattern``."""
    parts = _split_rel(rel_dir) if rel_dir else ()
    try:
        base = resolved_path(root, *parts)
    except PathTraversalError:
        return []
    if not os.path.isdir(base):
        return []
    out: list[str] = []
    for name in sorted(os.listdir(base)):
        if not fnmatch.fnmatch(name, pattern):
            continue
        child_parts = (*parts, name) if parts else (name,)
        rel = "/".join(child_parts)
        if isfile_at(root, *child_parts):
            out.append(rel)
    return out


def iter_pack_files(
    root: str | Path,
    *,
    skip_dir_names: set[str] | frozenset[str],
    skip_file_names: set[str] | frozenset[str],
) -> Iterator[tuple[str, int]]:
    """Yield ``(relative_posix_path, size)`` under pack ``root`` without symlink escape."""
    base = _root_base(root)
    pending: list[tuple[str, ...]] = [()]
    while pending:
        rel_parts = pending.pop()
        try:
            dir_path = resolved_path(root, *rel_parts) if rel_parts else base
        except PathTraversalError:
            continue
        if not os.path.isdir(dir_path):
            continue
        try:
            names = sorted(os.listdir(dir_path))
        except OSError:
            continue
        subdirs: list[tuple[str, ...]] = []
        for name in names:
            child_parts = (*rel_parts, name)
            try:
                child_path = resolved_path(root, *child_parts)
            except PathTraversalError:
                continue
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
