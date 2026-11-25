"""Read and write eval packs on disk."""

from __future__ import annotations

import fnmatch
import hashlib
from pathlib import Path
from typing import Any

from skillgate_ai.pack.constants import (
    _SKIP_DIR_NAMES,
    _SKIP_FILE_NAMES,
    ASSET_DIR,
    CASE_SUFFIXES,
    DEFAULT_FIXTURE_GLOB,
    GOLDEN_DIR,
    IMAGE_SUFFIXES,
    PDF_DEMO_FIXTURE_NAMES,
)
from skillgate_ai.pack.pathsafe import _rel_to_skill, try_resolve_pack_root
from skillgate_ai.pack.samples import is_authentic_fixture_bytes
from skillgate_ai.pack_io import is_pack_file, read_pack_bytes
from skillgate_ai.paths import PathTraversalError, pack_file_at, require_under


def list_pack_files(skill_path: str | Path) -> list[dict[str, Any]]:
    """Relative paths from the skill root (SKILL.md itself is omitted)."""
    root = try_resolve_pack_root(skill_path)
    if root is None:
        return []
    found: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        try:
            safe = require_under(root, path)
        except PathTraversalError:
            continue
        if not safe.is_file():
            continue
        rel = _rel_to_skill(root, safe)
        if rel is None:
            continue
        if rel == "SKILL.md" or rel.lower() in _SKIP_FILE_NAMES:
            continue
        if any(part.lower() in _SKIP_DIR_NAMES for part in Path(rel).parts):
            continue
        found.append({"path": rel, "bytes": safe.stat().st_size})
    return found


def fixture_files(skill_path: str | Path) -> list[dict[str, Any]]:
    """Files agentskills would treat as input resources: evals/, assets/."""
    out: list[dict[str, Any]] = []
    for item in list_pack_files(skill_path):
        path = item["path"]
        if path.startswith(("evals/", f"{ASSET_DIR}/")):
            out.append(item)
    return out


def relevant_eval_fixtures(
    skill_path: str | Path,
    glob_pat: str | None = None,
) -> list[dict[str, Any]]:
    """Dataset files under the pack (default evals/fixtures/*).

    Skips standup/prompt ``.md`` cases and unauthentic PDF/image stand-ins.
    """
    root = try_resolve_pack_root(skill_path)
    if root is None:
        return []
    pattern = (glob_pat or DEFAULT_FIXTURE_GLOB).replace("\\", "/").strip()
    if not pattern:
        pattern = DEFAULT_FIXTURE_GLOB
    found: list[dict[str, Any]] = []
    for item in list_pack_files(root):
        rel = str(item["path"]).replace("\\", "/")
        if rel.startswith(f"{GOLDEN_DIR}/") or rel == GOLDEN_DIR:
            continue
        if not _glob_match(rel, pattern):
            continue
        suffix = Path(rel).suffix.lower()
        if suffix in CASE_SUFFIXES:
            continue
        if not is_pack_file(root, rel):
            continue
        data = read_pack_bytes(root, rel)
        if suffix in IMAGE_SUFFIXES or suffix == ".pdf":
            if not is_authentic_fixture_bytes(rel, data):
                continue
        elif len(data) < 1:
            continue
        found.append({"src": rel, "dest": Path(rel).name, "bytes": len(data)})
    return _without_leaked_pdf_demo(root, found)


def _glob_match(rel: str, pattern: str) -> bool:
    if fnmatch.fnmatch(rel, pattern):
        return True
    name = Path(rel).name
    if fnmatch.fnmatch(name, pattern):
        return True
    if pattern.endswith("/**"):
        prefix = pattern[:-3].rstrip("/")
        return rel == prefix or rel.startswith(prefix + "/")
    return False


def skill_pack_hash(skill_path: str | Path | None) -> str:
    """Stable hash of the skill directory so fixtures version with the skill."""
    if not skill_path:
        return ""
    root = try_resolve_pack_root(skill_path)
    if root is None:
        return ""
    digest = hashlib.sha256()
    for item in list_pack_files(root):
        rel = item["path"]
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        if not is_pack_file(root, rel):
            continue
        digest.update(read_pack_bytes(root, rel))
        digest.update(b"\0")
    if is_pack_file(root, "SKILL.md"):
        digest.update(b"SKILL.md\0")
        digest.update(read_pack_bytes(root, "SKILL.md"))
    return digest.hexdigest()


def _is_pdf_example_dir(root: Path) -> bool:
    return root.name in {"pdf", "pdf-sabotaged"}


def _without_leaked_pdf_demo(root: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop the pdf example's five fixtures when they show up on another skill."""
    if _is_pdf_example_dir(root):
        return rows
    names = {Path(str(row.get("src") or "")).name for row in rows}
    if not names >= PDF_DEMO_FIXTURE_NAMES:
        return rows
    return [
        row for row in rows if Path(str(row.get("src") or "")).name not in PDF_DEMO_FIXTURE_NAMES
    ]


def browser_files(skill_path: str | Path) -> list[dict[str, Any]]:
    """Pack listing for the repository skill detail (includes SKILL.md)."""
    root = try_resolve_pack_root(skill_path)
    if root is None:
        return []
    items: list[dict[str, Any]] = []
    if is_pack_file(root, "SKILL.md"):
        import os

        skill_md = pack_file_at(root, "SKILL.md")
        items.append({"path": "SKILL.md", "bytes": os.path.getsize(os.fsdecode(skill_md))})
    items.extend(list_pack_files(root))
    return items
