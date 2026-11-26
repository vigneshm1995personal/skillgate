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


def _anchor(root: str | Path) -> Path:
    text = str(root)
    if ".." in Path(text).parts:
        raise PathTraversalError("Path escapes the allowed root.")
    resolved_name = os.path.realpath(os.path.expanduser(text))
    return Path(resolved_name)


def _safe_target(root: str | Path, *rel_parts: str) -> Path:
    base = _anchor(root)
    if not rel_parts:
        return base
    _reject_escape_parts(*rel_parts)
    target = base.joinpath(*rel_parts).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise PathTraversalError("Path escapes the allowed root.") from exc
    return target


def resolved_path(root: str | Path, *rel_parts: str) -> str:
    return str(_safe_target(root, *rel_parts))


def resolved_relative(root: str | Path, rel: str) -> str:
    return resolved_path(root, *_split_rel(rel))


def is_root_directory(root: str | Path) -> bool:
    try:
        target = _safe_target(root)
    except (PathTraversalError, OSError):
        return False
    return target.is_dir()


def isfile_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        base = _anchor(root)
        target = _safe_target(root, *rel_parts)
        target.relative_to(base)
    except (PathTraversalError, OSError, ValueError):
        return False
    return target.is_file()


def isdir_at(root: str | Path, *rel_parts: str) -> bool:
    try:
        base = _anchor(root)
        target = _safe_target(root, *rel_parts)
        target.relative_to(base)
    except (PathTraversalError, OSError, ValueError):
        return False
    return target.is_dir()


def file_size(root: str | Path, *rel_parts: str) -> int:
    base = _anchor(root)
    target = _safe_target(root, *rel_parts)
    target.relative_to(base)
    return target.stat().st_size


def read_text(root: str | Path, *rel_parts: str, encoding: str = "utf-8") -> str:
    base = _anchor(root)
    target = _safe_target(root, *rel_parts)
    target.relative_to(base)
    with target.open(encoding=encoding) as handle:
        return handle.read()


def read_bytes_at(root: str | Path, *rel_parts: str) -> bytes:
    base = _anchor(root)
    target = _safe_target(root, *rel_parts)
    target.relative_to(base)
    with target.open("rb") as handle:
        return handle.read()


def write_text(root: str | Path, *rel_parts: str, text: str, encoding: str = "utf-8") -> str:
    base = _anchor(root)
    target = _safe_target(root, *rel_parts)
    target.relative_to(base)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding=encoding) as handle:
        handle.write(text)
    return str(target)


def write_bytes_at(root: str | Path, *rel_parts: str, data: bytes) -> str:
    base = _anchor(root)
    target = _safe_target(root, *rel_parts)
    target.relative_to(base)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as handle:
        handle.write(data)
    return str(target)


def append_text_line(root: str | Path, *rel_parts: str, line: str, encoding: str = "utf-8") -> str:
    base = _anchor(root)
    target = _safe_target(root, *rel_parts)
    target.relative_to(base)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding=encoding) as handle:
        handle.write(line)
    return str(target)


def list_names(root: str | Path, *rel_dir_parts: str) -> list[str]:
    base = _anchor(root)
    target = _safe_target(root, *rel_dir_parts)
    target.relative_to(base)
    if not target.is_dir():
        return []
    return sorted(child.name for child in target.iterdir())


def glob_files(root: str | Path, rel_dir: str, pattern: str) -> list[str]:
    parts = _split_rel(rel_dir) if rel_dir else ()
    try:
        base = _anchor(root)
        dir_path = _safe_target(root, *parts)
        dir_path.relative_to(base)
    except (PathTraversalError, ValueError):
        return []
    if not dir_path.is_dir():
        return []
    out: list[str] = []
    for child in sorted(dir_path.iterdir(), key=lambda entry: entry.name):
        if not fnmatch.fnmatch(child.name, pattern):
            continue
        child_parts = (*parts, child.name) if parts else (child.name,)
        if isfile_at(root, *child_parts):
            out.append("/".join(child_parts))
    return out


def iter_pack_files(
    root: str | Path,
    *,
    skip_dir_names: set[str] | frozenset[str],
    skip_file_names: set[str] | frozenset[str],
) -> Iterator[tuple[str, int]]:
    """Yield ``(relative_posix_path, size)`` under pack ``root`` without symlink escape."""
    pack_base = _anchor(root)
    pending: list[tuple[str, ...]] = [()]
    while pending:
        rel_parts = pending.pop()
        try:
            dir_path = _safe_target(root, *rel_parts) if rel_parts else pack_base
            dir_path.relative_to(pack_base)
        except (PathTraversalError, ValueError):
            continue
        if not dir_path.is_dir():
            continue
        subdirs: list[tuple[str, ...]] = []
        for child in sorted(dir_path.iterdir(), key=lambda entry: entry.name):
            child_parts = (*rel_parts, child.name)
            try:
                child_path = _safe_target(root, *child_parts)
                child_path.relative_to(pack_base)
            except (PathTraversalError, ValueError):
                continue
            if child_path.is_dir():
                if child.name.lower() not in skip_dir_names:
                    subdirs.append(child_parts)
                continue
            if not child_path.is_file():
                continue
            rel = "/".join(child_parts)
            if rel == "SKILL.md" or rel.lower() in skip_file_names:
                continue
            if any(p.lower() in skip_dir_names for p in rel_parts):
                continue
            try:
                size = child_path.stat().st_size
            except OSError:
                continue
            yield rel, size
        pending.extend(reversed(subdirs))
