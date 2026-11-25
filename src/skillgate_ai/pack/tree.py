"""Read and write eval packs on disk."""

from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from skillgate_ai.pack.constants import (
    _SKIP_DIR_NAMES,
    _SKIP_FILE_NAMES,
    IMAGE_SUFFIXES,
    PREVIEW_TEXT_LIMIT,
    TEXT_SUFFIXES,
)
from skillgate_ai.pack.listing import browser_files
from skillgate_ai.pack.pathsafe import _path_under_skill, resolve_pack_root


def copy_skill_pack(
    source: str | Path,
    dest: str | Path,
    *,
    include_goldens: bool = False,
    include_evals: bool | None = None,
) -> dict[str, Any]:
    """Recursive copy of a skill pack root, preserving the relative tree.

    Default (deploy / sandbox): SKILL.md, scripts/, assets/, references/, and
    other non-eval files. ``evals/`` stays in the source pack.

    Import into this project passes ``include_goldens=True`` so checks can score.
    """
    src = Path(source).expanduser().resolve()
    dst = Path(dest).expanduser().resolve()
    if not src.is_dir():
        raise FileNotFoundError(str(src))
    if src == dst:
        raise ValueError("Install source and dest are the same folder.")
    parent = dst.parent
    parent.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex[:10]
    tmp = parent / f".{dst.name}.skillgate-tmp-{token}"
    old = parent / f".{dst.name}.skillgate-old-{token}"

    keep_evals = include_goldens if include_evals is None else include_evals

    def ignore(_directory: str, names: list[str]) -> set[str]:
        return _pack_copy_ignore(
            _directory,
            names,
            include_evals=keep_evals,
            include_goldens=include_goldens,
        )

    try:
        if tmp.exists():
            shutil.rmtree(tmp)
        shutil.copytree(src, tmp, ignore=ignore)
        if dst.exists():
            dst.rename(old)
            try:
                tmp.rename(dst)
            except OSError:
                if old.exists() and not dst.exists():
                    old.rename(dst)
                raise
            shutil.rmtree(old, ignore_errors=True)
        else:
            tmp.rename(dst)
    except BaseException:
        if tmp.exists() and tmp.resolve() != dst:
            shutil.rmtree(tmp, ignore_errors=True)
        raise
    return {
        "pack_path": str(src),
        "dest_path": str(dst),
        "file_count": len(browser_files(dst)),
    }


def pack_file_path(skill_path: str | Path, rel: str) -> Path:
    from skillgate_ai.paths import require_under

    root = resolve_pack_root(skill_path)
    candidate = _path_under_skill(root, rel)
    if candidate is None or not candidate.is_file():
        raise FileNotFoundError(rel)
    return require_under(root, candidate)


def pack_preview(skill_path: str | Path, rel: str) -> dict[str, Any]:
    path = pack_file_path(skill_path, rel)
    data = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix in IMAGE_SUFFIXES:
        kind = "image"
    elif suffix == ".pdf":
        kind = "pdf"
    elif suffix in TEXT_SUFFIXES or b"\0" not in data[:1024]:
        kind = "text"
        try:
            data.decode("utf-8")
        except UnicodeDecodeError:
            kind = "binary"
    else:
        kind = "binary"
    payload: dict[str, Any] = {
        "path": rel.replace("\\", "/").lstrip("/"),
        "bytes": len(data),
        "kind": kind,
        "content_type": _content_type(suffix, kind),
    }
    if kind == "text":
        payload["text"] = data.decode("utf-8", errors="replace")[:PREVIEW_TEXT_LIMIT]
    return payload


def _content_type(suffix: str, kind: str) -> str:
    mapping = {
        ".md": "text/markdown",
        ".txt": "text/plain",
        ".json": "application/json",
        ".yaml": "text/yaml",
        ".yml": "text/yaml",
        ".csv": "text/csv",
        ".py": "text/x-python",
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".svg": "image/svg+xml",
    }
    if suffix in mapping:
        return mapping[suffix]
    if kind == "text":
        return "text/plain"
    return "application/octet-stream"


def _pack_copy_ignore(
    directory: str,
    names: list[str],
    *,
    include_evals: bool = False,
    include_goldens: bool = False,
) -> set[str]:
    ignored: set[str] = set()
    parent = Path(directory).name.lower()
    for name in names:
        key = name.lower()
        if key in _SKIP_DIR_NAMES or key in _SKIP_FILE_NAMES:
            ignored.add(name)
        if not include_evals and key == "evals":
            ignored.add(name)
        if include_evals and not include_goldens and parent == "evals" and key == "goldens":
            ignored.add(name)
    return ignored
