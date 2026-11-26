"""Filesystem I/O and checks under a trusted root with inline containment."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Iterator
from pathlib import Path

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


def _contained_target(root: str | Path, *rel_parts: str) -> str:
    """Return a canonical path under ``root``; barrier uses ``realpath`` + ``commonpath``."""
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base = os.path.realpath(os.path.expanduser(text))
    joined = os.path.join(base, *rel_parts) if rel_parts else base
    target = os.path.realpath(joined)
    try:
        if os.path.commonpath([base, target]) != base:
            raise PathTraversalError("Path escapes the allowed root.")
    except ValueError as exc:
        raise PathTraversalError("Path escapes the allowed root.") from exc
    return target


def resolved_path(root: str | Path, *rel_parts: str) -> str:
    return _contained_target(root, *rel_parts)


def resolved_relative(root: str | Path, rel: str) -> str:
    return resolved_path(root, *_split_rel(rel))


def is_root_directory(root: str | Path) -> bool:
    try:
        target = _contained_target(root)
    except (PathTraversalError, OSError):
        return False
    return os.path.isdir(target)


def isfile_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        target = _contained_target(root, *rel_parts)
    except (PathTraversalError, OSError, ValueError):
        return False
    return os.path.isfile(target)


def isdir_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        target = _contained_target(root, *rel_parts)
    except (PathTraversalError, OSError, ValueError):
        return False
    return os.path.isdir(target)


def file_size(root: str | Path, *rel_parts: str) -> int:
    target = _contained_target(root, *rel_parts)
    return os.path.getsize(target)


def read_text(root: str | Path, *rel_parts: str, encoding: str = "utf-8") -> str:
    target = _contained_target(root, *rel_parts)
    with open(target, encoding=encoding) as handle:
        return handle.read()


def read_bytes_at(root: str | Path, *rel_parts: str) -> bytes:
    target = _contained_target(root, *rel_parts)
    with open(target, "rb") as handle:
        return handle.read()


def write_text(root: str | Path, *rel_parts: str, text: str, encoding: str = "utf-8") -> str:
    target = _contained_target(root, *rel_parts)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding=encoding) as handle:
        handle.write(text)
    return target


def write_bytes_at(root: str | Path, *rel_parts: str, data: bytes) -> str:
    target = _contained_target(root, *rel_parts)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(data)
    return target


def append_text_line(root: str | Path, *rel_parts: str, line: str, encoding: str = "utf-8") -> str:
    target = _contained_target(root, *rel_parts)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "a", encoding=encoding) as handle:
        handle.write(line)
    return target


def list_names(root: str | Path, *rel_dir_parts: str) -> list[str]:
    target = _contained_target(root, *rel_dir_parts)
    if not os.path.isdir(target):
        return []
    return sorted(name for name in os.listdir(target))


def glob_files(root: str | Path, rel_dir: str, pattern: str) -> list[str]:
    parts = _split_rel(rel_dir) if rel_dir else ()
    try:
        dir_path = _contained_target(root, *parts)
    except (PathTraversalError, ValueError):
        return []
    if not os.path.isdir(dir_path):
        return []
    out: list[str] = []
    for name in sorted(os.listdir(dir_path)):
        if not fnmatch.fnmatch(name, pattern):
            continue
        child_parts = (*parts, name) if parts else (name,)
        if isfile_at(root, *child_parts):
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
    pack_base = _contained_target(anchor, *pack_prefix)
    pending: list[tuple[str, ...]] = [()]
    while pending:
        rel_parts = pending.pop()
        try:
            dir_path = (
                _contained_target(anchor, *pack_prefix, *rel_parts) if rel_parts else pack_base
            )
            if os.path.commonpath([pack_base, dir_path]) != pack_base:
                continue
        except (PathTraversalError, ValueError, OSError):
            continue
        if not os.path.isdir(dir_path):
            continue
        subdirs: list[tuple[str, ...]] = []
        for name in sorted(os.listdir(dir_path)):
            child_parts = (*rel_parts, name)
            try:
                child_path = _contained_target(anchor, *pack_prefix, *child_parts)
                if os.path.commonpath([pack_base, child_path]) != pack_base:
                    continue
            except (PathTraversalError, ValueError, OSError):
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
