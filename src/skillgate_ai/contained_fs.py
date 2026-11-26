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


def resolved_path(root: str | Path, *rel_parts: str) -> str:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base = os.path.realpath(os.path.expanduser(text))
    joined = os.path.join(base, *rel_parts) if rel_parts else base
    target = os.path.realpath(joined)
    anchor = os.path.normpath(base)
    if not (target == anchor or target.startswith(anchor + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    return target


def resolved_relative(root: str | Path, rel: str) -> str:
    return resolved_path(root, *_split_rel(rel))


def is_root_directory(root: str | Path) -> bool:
    try:
        text = str(root)
        if ".." in Path(text).parts:
            return False
        base = os.path.realpath(os.path.expanduser(text))
        target = os.path.realpath(base)
        anchor = os.path.normpath(base)
        if not (target == anchor or target.startswith(anchor + os.sep)):
            return False
    except (PathTraversalError, OSError, ValueError):
        return False
    return os.path.isdir(target)


def isfile_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        text = str(root)
        if ".." in Path(text).parts:
            return False
        _reject_escape_parts(*rel_parts)
        base = os.path.realpath(os.path.expanduser(text))
        joined = os.path.join(base, *rel_parts) if rel_parts else base
        target = os.path.realpath(joined)
        anchor = os.path.normpath(base)
        if not (target == anchor or target.startswith(anchor + os.sep)):
            return False
    except (PathTraversalError, OSError, ValueError):
        return False
    return os.path.isfile(target)


def isdir_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        text = str(root)
        if ".." in Path(text).parts:
            return False
        _reject_escape_parts(*rel_parts)
        base = os.path.realpath(os.path.expanduser(text))
        joined = os.path.join(base, *rel_parts) if rel_parts else base
        target = os.path.realpath(joined)
        anchor = os.path.normpath(base)
        if not (target == anchor or target.startswith(anchor + os.sep)):
            return False
    except (PathTraversalError, OSError, ValueError):
        return False
    return os.path.isdir(target)


def file_size(root: str | Path, *rel_parts: str) -> int:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base = os.path.realpath(os.path.expanduser(text))
    joined = os.path.join(base, *rel_parts) if rel_parts else base
    target = os.path.realpath(joined)
    anchor = os.path.normpath(base)
    if not (target == anchor or target.startswith(anchor + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    return os.path.getsize(target)


def read_text(root: str | Path, *rel_parts: str, encoding: str = "utf-8") -> str:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base = os.path.realpath(os.path.expanduser(text))
    joined = os.path.join(base, *rel_parts) if rel_parts else base
    target = os.path.realpath(joined)
    anchor = os.path.normpath(base)
    if not (target == anchor or target.startswith(anchor + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    with open(target, encoding=encoding) as handle:
        return handle.read()


def read_bytes_at(root: str | Path, *rel_parts: str) -> bytes:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base = os.path.realpath(os.path.expanduser(text))
    joined = os.path.join(base, *rel_parts) if rel_parts else base
    target = os.path.realpath(joined)
    anchor = os.path.normpath(base)
    if not (target == anchor or target.startswith(anchor + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    with open(target, "rb") as handle:
        return handle.read()


def write_text(root: str | Path, *rel_parts: str, text: str, encoding: str = "utf-8") -> str:
    text_root = str(root)
    if ".." in Path(text_root).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base = os.path.realpath(os.path.expanduser(text_root))
    joined = os.path.join(base, *rel_parts) if rel_parts else base
    target = os.path.realpath(joined)
    anchor = os.path.normpath(base)
    if not (target == anchor or target.startswith(anchor + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding=encoding) as handle:
        handle.write(text)
    return target


def write_bytes_at(root: str | Path, *rel_parts: str, data: bytes) -> str:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base = os.path.realpath(os.path.expanduser(text))
    joined = os.path.join(base, *rel_parts) if rel_parts else base
    target = os.path.realpath(joined)
    anchor = os.path.normpath(base)
    if not (target == anchor or target.startswith(anchor + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as handle:
        handle.write(data)
    return target


def append_text_line(root: str | Path, *rel_parts: str, line: str, encoding: str = "utf-8") -> str:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base = os.path.realpath(os.path.expanduser(text))
    joined = os.path.join(base, *rel_parts) if rel_parts else base
    target = os.path.realpath(joined)
    anchor = os.path.normpath(base)
    if not (target == anchor or target.startswith(anchor + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "a", encoding=encoding) as handle:
        handle.write(line)
    return target


def list_names(root: str | Path, *rel_dir_parts: str) -> list[str]:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_dir_parts)
    base = os.path.realpath(os.path.expanduser(text))
    joined = os.path.join(base, *rel_dir_parts) if rel_dir_parts else base
    target = os.path.realpath(joined)
    anchor = os.path.normpath(base)
    if not (target == anchor or target.startswith(anchor + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    if not os.path.isdir(target):
        return []
    return sorted(name for name in os.listdir(target))


def glob_files(root: str | Path, rel_dir: str, pattern: str) -> list[str]:
    parts = _split_rel(rel_dir) if rel_dir else ()
    try:
        text = str(root)
        if ".." in Path(text).parts:
            return []
        _reject_escape_parts(*parts)
        base = os.path.realpath(os.path.expanduser(text))
        joined = os.path.join(base, *parts) if parts else base
        dir_path = os.path.realpath(joined)
        anchor = os.path.normpath(base)
        if not (dir_path == anchor or dir_path.startswith(anchor + os.sep)):
            return []
    except (PathTraversalError, ValueError):
        return []
    if not os.path.isdir(dir_path):
        return []
    out: list[str] = []
    for name in sorted(os.listdir(dir_path)):
        if not fnmatch.fnmatch(name, pattern):
            continue
        child_parts = (*parts, name) if parts else (name,)
        joined_child = os.path.join(base, *child_parts) if child_parts else base
        child_target = os.path.realpath(joined_child)
        anchor = os.path.normpath(base)
        if not (child_target == anchor or child_target.startswith(anchor + os.sep)):
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
    anchor_text = str(anchor)
    if ".." in Path(anchor_text).parts:
        return
    _reject_escape_parts(*pack_prefix)
    pack_base = os.path.realpath(
        os.path.join(os.path.realpath(os.path.expanduser(anchor_text)), *pack_prefix)
    )
    pending: list[tuple[str, ...]] = [()]
    while pending:
        rel_parts = pending.pop()
        try:
            joined = os.path.join(pack_base, *rel_parts) if rel_parts else pack_base
            dir_path = os.path.realpath(joined)
            pack_root = os.path.normpath(pack_base)
            if not (dir_path == pack_root or dir_path.startswith(pack_root + os.sep)):
                continue
        except (PathTraversalError, ValueError, OSError):
            continue
        if not os.path.isdir(dir_path):
            continue
        subdirs: list[tuple[str, ...]] = []
        for name in sorted(os.listdir(dir_path)):
            child_parts = (*rel_parts, name)
            try:
                child_path = os.path.realpath(os.path.join(pack_base, *child_parts))
                pack_root = os.path.normpath(pack_base)
                if not (child_path == pack_root or child_path.startswith(pack_root + os.sep)):
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
