"""Read and write eval packs on disk."""

from __future__ import annotations

import re
from pathlib import Path

from skillgate_ai.pack.constants import (
    _SAFE_NAME,
    FIXTURE_DIR,
)


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
    candidate = (skill_root / "/".join(parts)).resolve()
    try:
        candidate.relative_to(skill_root.resolve())
    except ValueError:
        return None
    return candidate


def _rel_to_skill(root: Path, path: Path) -> str | None:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None


def _safe_filename(name: str) -> str:
    cleaned = _SAFE_NAME.sub("-", name).strip(".-") or "sample.txt"
    if cleaned in {".", ".."}:
        return "sample.txt"
    return cleaned[:80]
