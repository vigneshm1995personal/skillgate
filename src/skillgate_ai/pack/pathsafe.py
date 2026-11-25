"""Read and write eval packs on disk."""

from __future__ import annotations

import re
from pathlib import Path

from skillgate_ai.pack.constants import (
    _SAFE_NAME,
    FIXTURE_DIR,
)
from skillgate_ai.paths import PathTraversalError, contained_path, skill_pack_root


def resolve_pack_root(skill_path: str | Path) -> Path:
    """Resolved skill pack directory (must exist)."""
    try:
        root = skill_pack_root(skill_path)
    except PathTraversalError as exc:
        raise ValueError("Skill folder not found.") from exc
    import os

    if not os.path.isdir(os.path.realpath(os.path.expanduser(str(root)))):
        raise ValueError("Skill folder not found.")
    return root


def try_resolve_pack_root(skill_path: str | Path) -> Path | None:
    """Like ``resolve_pack_root`` but returns None when the path is missing or not a directory."""
    try:
        return resolve_pack_root(skill_path)
    except (OSError, ValueError):
        return None


def safe_relpath(rel: str, *, default_dir: str = FIXTURE_DIR) -> str:
    """Keep a path inside the skill folder. Default to evals/fixtures/<name>."""
    cleaned = (rel or "").replace("\\", "/").strip()
    cleaned = cleaned.lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ""}]
    if any(p == ".." for p in parts):
        raise ValueError("Path must stay inside the skill folder.")
    if not parts:
        raise ValueError("A file path is required.")
    if len(parts) == 1:
        name = _safe_filename(parts[0])
        if name.lower() == "skill.md":
            return "SKILL.md"
        return f"{default_dir}/{name}"
    parts[-1] = _safe_filename(parts[-1])
    return "/".join(parts)


def is_pack_relative(src: str) -> bool:
    """True when src is a skill-root relative path (never absolute, never ..)."""
    cleaned = (src or "").replace("\\", "/").strip()
    if not cleaned:
        return False
    if Path(cleaned).is_absolute() or cleaned.startswith("/"):
        return False
    parts = [p for p in cleaned.split("/") if p]
    return bool(parts) and not any(p == ".." for p in parts)


def fixture_src_for(src: str, dest: str = "") -> str:
    """Pack-relative evals/fixtures/<name> for a check file that must be rewritten."""
    name = Path(dest or src).name or "sample.bin"
    return f"{FIXTURE_DIR}/{_safe_filename(name)}"


def implied_fixture_name(text: str) -> str:
    blob = text or ""
    if re.search(r"\bpdf\b", blob, re.IGNORECASE):
        return "sample.pdf"
    if re.search(r"\bcsv\b", blob, re.IGNORECASE):
        return "sample.csv"
    if re.search(r"\bjson\b", blob, re.IGNORECASE):
        return "sample.json"
    if re.search(
        r"\b(image|images|photo|photos|png|jpe?g|screenshot|scan|scans)\b", blob, re.IGNORECASE
    ):
        return "sample.png"
    return "sample.txt"


def _path_under_skill(skill_root: Path, rel: str) -> Path | None:
    cleaned = rel.replace("\\", "/").strip().lstrip("/")
    parts = [p for p in cleaned.split("/") if p and p not in {".", ""}]
    if not parts or any(p == ".." for p in parts):
        return None
    try:
        return contained_path(skill_root, *parts)
    except PathTraversalError:
        return None


def _rel_to_skill(root: Path, path: Path) -> str | None:
    import os

    from skillgate_ai.paths import PathTraversalError, require_under

    try:
        safe = require_under(root, path)
        base = os.path.realpath(os.path.expanduser(str(root)))
        target = os.path.realpath(os.fsdecode(safe))
        rel = os.path.relpath(target, base)
    except (PathTraversalError, ValueError, OSError):
        return None
    if rel.startswith(".."):
        return None
    return rel.replace("\\", "/")


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME.sub("-", name).strip(".-") or "sample.txt"
    if cleaned in {".", ".."}:
        return "sample.txt"
    return cleaned[:80]
