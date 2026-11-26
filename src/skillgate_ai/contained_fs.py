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


def resolved_relative(root: str | Path, rel: str) -> str:
    from skillgate_ai.paths import filesystem_path_under

    return filesystem_path_under(root, *_split_rel(rel))


def is_root_directory(root: str | Path) -> bool:
    try:
        text = str(root)
        if ".." in Path(text).parts:
            return False
        base_path = os.path.normpath(os.path.realpath(text))
        fullpath = os.path.normpath(os.path.realpath(base_path))
        if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
            return False
        return os.path.isdir(fullpath)
    except (OSError, ValueError):
        return False


def isfile_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        text = str(root)
        if ".." in Path(text).parts:
            return False
        _reject_escape_parts(*rel_parts)
        base_path = os.path.normpath(os.path.realpath(text))
        joined = os.path.join(base_path, *rel_parts) if rel_parts else base_path
        fullpath = os.path.normpath(os.path.realpath(joined))
        if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
            return False
        return os.path.isfile(fullpath)
    except (PathTraversalError, OSError, ValueError):
        return False


def isdir_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        text = str(root)
        if ".." in Path(text).parts:
            return False
        _reject_escape_parts(*rel_parts)
        base_path = os.path.normpath(os.path.realpath(text))
        joined = os.path.join(base_path, *rel_parts) if rel_parts else base_path
        fullpath = os.path.normpath(os.path.realpath(joined))
        if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
            return False
        return os.path.isdir(fullpath)
    except (PathTraversalError, OSError, ValueError):
        return False


def file_size(root: str | Path, *rel_parts: str) -> int:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base_path = os.path.normpath(os.path.realpath(text))
    joined = os.path.join(base_path, *rel_parts) if rel_parts else base_path
    fullpath = os.path.normpath(os.path.realpath(joined))
    if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    return os.path.getsize(fullpath)


def read_text(root: str | Path, *rel_parts: str, encoding: str = "utf-8") -> str:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base_path = os.path.normpath(os.path.realpath(text))
    joined = os.path.join(base_path, *rel_parts) if rel_parts else base_path
    fullpath = os.path.normpath(os.path.realpath(joined))
    if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    with open(fullpath, encoding=encoding) as handle:
        return handle.read()


def read_bytes_at(root: str | Path, *rel_parts: str) -> bytes:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base_path = os.path.normpath(os.path.realpath(text))
    joined = os.path.join(base_path, *rel_parts) if rel_parts else base_path
    fullpath = os.path.normpath(os.path.realpath(joined))
    if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    with open(fullpath, "rb") as handle:
        return handle.read()


def write_text(root: str | Path, *rel_parts: str, text: str, encoding: str = "utf-8") -> str:
    text_root = str(root)
    if ".." in Path(text_root).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base_path = os.path.normpath(os.path.realpath(text_root))
    joined = os.path.join(base_path, *rel_parts) if rel_parts else base_path
    fullpath = os.path.normpath(os.path.realpath(joined))
    if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    with open(fullpath, "w", encoding=encoding) as handle:
        handle.write(text)
    return fullpath


def write_bytes_at(root: str | Path, *rel_parts: str, data: bytes) -> str:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base_path = os.path.normpath(os.path.realpath(text))
    joined = os.path.join(base_path, *rel_parts) if rel_parts else base_path
    fullpath = os.path.normpath(os.path.realpath(joined))
    if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    with open(fullpath, "wb") as handle:
        handle.write(data)
    return fullpath


def append_text_line(root: str | Path, *rel_parts: str, line: str, encoding: str = "utf-8") -> str:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_parts)
    base_path = os.path.normpath(os.path.realpath(text))
    joined = os.path.join(base_path, *rel_parts) if rel_parts else base_path
    fullpath = os.path.normpath(os.path.realpath(joined))
    if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    os.makedirs(os.path.dirname(fullpath), exist_ok=True)
    with open(fullpath, "a", encoding=encoding) as handle:
        handle.write(line)
    return fullpath


def list_names(root: str | Path, *rel_dir_parts: str) -> list[str]:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    _reject_escape_parts(*rel_dir_parts)
    base_path = os.path.normpath(os.path.realpath(text))
    joined = os.path.join(base_path, *rel_dir_parts) if rel_dir_parts else base_path
    fullpath = os.path.normpath(os.path.realpath(joined))
    if not (fullpath == base_path or fullpath.startswith(base_path + os.sep)):
        raise PathTraversalError("Path escapes the allowed root.")
    if not os.path.isdir(fullpath):
        return []
    return sorted(name for name in os.listdir(fullpath))


def glob_files(root: str | Path, rel_dir: str, pattern: str) -> list[str]:
    parts = _split_rel(rel_dir) if rel_dir else ()
    try:
        text = str(root)
        if ".." in Path(text).parts:
            return []
        _reject_escape_parts(*parts)
        base_path = os.path.normpath(os.path.realpath(text))
        joined = os.path.join(base_path, *parts) if parts else base_path
        dir_path = os.path.normpath(os.path.realpath(joined))
        if not (dir_path == base_path or dir_path.startswith(base_path + os.sep)):
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
        joined_child = os.path.join(base_path, *child_parts) if child_parts else base_path
        child_target = os.path.normpath(os.path.realpath(joined_child))
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
    anchor_text = str(anchor)
    if ".." in Path(anchor_text).parts:
        return
    _reject_escape_parts(*pack_prefix)
    anchor_base = os.path.normpath(os.path.realpath(anchor_text))
    pack_base = os.path.normpath(os.path.realpath(os.path.join(anchor_base, *pack_prefix)))
    pending: list[tuple[str, ...]] = [()]
    while pending:
        rel_parts = pending.pop()
        try:
            joined = os.path.join(pack_base, *rel_parts) if rel_parts else pack_base
            dir_path = os.path.normpath(os.path.realpath(joined))
            if not (dir_path == pack_base or dir_path.startswith(pack_base + os.sep)):
                continue
        except (PathTraversalError, ValueError, OSError):
            continue
        if not os.path.isdir(dir_path):
            continue
        subdirs: list[tuple[str, ...]] = []
        for name in sorted(os.listdir(dir_path)):
            child_parts = (*rel_parts, name)
            try:
                child_path = os.path.normpath(
                    os.path.realpath(os.path.join(pack_base, *child_parts))
                )
                if not (child_path == pack_base or child_path.startswith(pack_base + os.sep)):
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