"""Paste / zip skill intake. Names cannot escape the workspace skills folder."""

from __future__ import annotations

import io
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from skillgate_ai.catalog import safe_skill_folder_name, workspace_skills_root
from skillgate_ai.errors import SkillGateError
from skillgate_ai.ingest import FRONTMATTER_RE, ingest_skill
from skillgate_ai.pack import copy_skill_pack
from skillgate_ai.pack_io import is_pack_file, write_pack_bytes, write_pack_text
from skillgate_ai.paths import PathTraversalError, contained_path, require_under
from skillgate_ai.scaffold import scaffold_trigger_cases

_GIT_URL_RE = re.compile(r"^(https?://|git@|ssh://).+", re.IGNORECASE)


def looks_like_git_url(text: str) -> bool:
    cleaned = (text or "").strip()
    if not cleaned:
        return False
    if _GIT_URL_RE.match(cleaned):
        return True
    return cleaned.endswith(".git")


def _inside(root: Path, candidate: Path) -> Path:
    return require_under(root, candidate)


def write_pasted_skill(root: Path, markdown: str) -> Path:
    text = markdown if markdown.endswith("\n") else markdown + "\n"
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise SkillGateError(
            "Paste a SKILL.md file that starts with YAML frontmatter.",
            hint="First line should be --- then name and description, then --- again.",
        )
    import yaml

    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        raise SkillGateError("SKILL.md frontmatter must be a mapping of fields.")
    display = str(parsed.get("name") or "").strip()
    name = safe_skill_folder_name(display)
    parent = require_under(root, workspace_skills_root(root))
    parent.mkdir(parents=True, exist_ok=True)
    dest = contained_path(parent, name)
    dest.mkdir(parents=True, exist_ok=True)
    write_pack_text(dest, "SKILL.md", text)
    ingest_skill(dest, strict=False)
    import os

    if not os.path.isdir(os.fsdecode(dest)):
        return dest
    if not is_pack_file(dest, "evals/cases.yaml"):
        scaffold_trigger_cases(dest)
    return dest


def _zip_rel(name: str, prefix: str) -> str | None:
    cleaned = name.replace("\\", "/").strip()
    if cleaned.startswith("/") or Path(cleaned).is_absolute():
        return None
    if ".." in Path(cleaned).parts:
        return None
    rel = cleaned[len(prefix) :].lstrip("/") if prefix and cleaned.startswith(prefix) else cleaned
    if not rel or rel.endswith("/"):
        return None
    if ".." in Path(rel).parts or Path(rel).is_absolute() or rel.startswith("/"):
        return None
    return rel


def extract_uploaded_skill(root: Path, data: bytes, *, filename: str) -> Path:
    parent = require_under(root, workspace_skills_root(root))
    parent.mkdir(parents=True, exist_ok=True)
    if filename.endswith(".md") or data.lstrip().startswith(b"---"):
        return write_pasted_skill(root, data.decode("utf-8"))
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SkillGateError("Upload a zip of a skill folder, or a SKILL.md file.") from exc
    skill_md = None
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if ".." in Path(name).parts or name.startswith("/") or Path(name).is_absolute():
            continue
        if name.endswith("SKILL.md") and not info.is_dir():
            skill_md = name
            break
    if not skill_md:
        raise SkillGateError("That zip has no SKILL.md.")
    parts = Path(skill_md).parts
    prefix = "/".join(parts[:-1])
    raw_folder = Path(parts[-2]).name if len(parts) >= 2 else Path(filename).stem
    folder_name = safe_skill_folder_name(raw_folder)
    dest = require_under(parent, parent / folder_name)
    if dest.exists():
        import shutil

        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for info in archive.infolist():
        name = info.filename.replace("\\", "/")
        if info.is_dir():
            continue
        rel = _zip_rel(name, prefix)
        if not rel:
            continue
        try:
            write_pack_bytes(dest, rel, archive.read(info))
        except PathTraversalError:
            continue
    ingest_skill(dest, strict=False)
    return dest


def import_skill_folder(root: Path, source: str | Path) -> Path:
    """Copy a local skill folder into ``<root>/skills/<slug>``."""
    import os

    from skillgate_ai.paths import skill_pack_root

    src = skill_pack_root(source)
    if not os.path.isdir(os.fsdecode(src)) or not is_pack_file(src, "SKILL.md"):
        raise SkillGateError(
            "Pass a skill folder that contains SKILL.md.",
            hint="Example: skillgate import ./my-skill",
        )
    loaded = ingest_skill(src, strict=False)
    slug = safe_skill_folder_name(loaded.name or src.name)
    parent = require_under(root, workspace_skills_root(root))
    parent.mkdir(parents=True, exist_ok=True)
    dest = require_under(parent, parent / slug)
    if os.path.exists(os.fsdecode(dest)):
        raise SkillGateError(
            f"{slug} is already in this project.",
            hint="Leave that folder as it is, or import a different skill.",
            exit_code=2,
        )
    copy_skill_pack(src, dest, include_goldens=True)
    ingest_skill(dest, strict=False)
    return dest


def import_skills_from_git(root: Path, repo_url: str) -> list[Path]:
    """Clone a repo and import skill pack(s) from its root or ``skills/``."""
    from skillgate_ai.sync import _clone, _reject_symlinks, _skill_names

    url = (repo_url or "").strip()
    if not looks_like_git_url(url):
        raise SkillGateError(
            "Pass a git URL to clone.",
            hint="Example: skillgate import https://github.com/org/skills.git",
        )
    with tempfile.TemporaryDirectory(prefix="sg-import-") as td:
        work = Path(td)
        _clone(url, work)
        if is_pack_file(work, "SKILL.md"):
            _reject_symlinks(work)
            return [import_skill_folder(root, work)]
        names = _skill_names(work, "skills")
        if not names:
            raise SkillGateError(
                "That repo has no SKILL.md at the root and no skills/ folder.",
                hint="Point at a single-skill repo or a monorepo with skills/<name>/SKILL.md.",
            )
        imported: list[Path] = []
        for name in names:
            skill_dir = work / "skills" / name
            _reject_symlinks(skill_dir)
            imported.append(import_skill_folder(root, skill_dir))
        return imported


def import_path_or_git_result(root: Path, target: str) -> dict[str, Any]:
    """CLI/API helper: one folder path or git URL."""
    from skillgate_ai.catalog import catalog_entries

    text = (target or "").strip()
    if not text:
        raise SkillGateError("Pass a skill folder or a git URL.")
    if looks_like_git_url(text):
        paths = import_skills_from_git(root, text)
        source = "git"
    else:
        paths = [import_skill_folder(root, text)]
        source = "folder"
    imported: list[dict[str, str]] = []
    for dest in paths:
        loaded = ingest_skill(dest, strict=False)
        imported.append(
            {
                "name": loaded.display_name or dest.name,
                "slug": loaded.name or dest.name,
                "source": source,
                "warning": loaded.warning or "",
            }
        )
    return {
        "imported": imported,
        "skipped": [],
        "skills": catalog_entries(root),
    }
