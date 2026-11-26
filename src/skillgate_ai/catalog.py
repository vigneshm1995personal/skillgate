"""Skill catalog: project ``skills/`` plus Cursor / Codex / Claude folders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skillgate_ai.deploy import claude_skills_root, codex_skills_root, cursor_skills_root
from skillgate_ai.errors import SkillGateError
from skillgate_ai.ingest import NAME_RE, folder_slug, ingest_skill
from skillgate_ai.pack import copy_skill_pack as copy_pack
from skillgate_ai.pack_io import is_pack_file
from skillgate_ai.paths import (
    PathTraversalError,
    contained_path,
    is_skill_pack,
    is_under_root,
    require_under,
)

SOURCE_ROOTS = (
    ("workspace", None),
    ("cursor", cursor_skills_root),
    ("codex", codex_skills_root),
    ("claude", claude_skills_root),
)

SOURCE_LABELS = {
    "workspace": "this project",
    "cursor": "Editor agent",
    "codex": "Terminal agent",
    "claude": "Code agent",
}


def workspace_skills_root(root: Path) -> Path:
    return (root / "skills").resolve()


def source_dir(source: str, *, root: Path) -> Path:
    key = (source or "").strip().lower()
    if key == "workspace":
        return workspace_skills_root(root)
    if key == "cursor":
        return cursor_skills_root()
    if key == "codex":
        return codex_skills_root()
    if key == "claude":
        return claude_skills_root()
    raise SkillGateError("Import source must be an agent folder or this project.")


def _iter_skill_dirs(parent: Path) -> list[Path]:
    if not parent.is_dir():
        return []
    found: list[Path] = []
    try:
        children = sorted(parent.iterdir())
    except OSError:
        return []
    for child in children:
        if child.is_dir() and (child / "SKILL.md").is_file():
            found.append(child.resolve())
    return found


def _workspace_skill_dir(path: Path, root: Path) -> Path | None:
    """Resolved skill folder when it and its SKILL.md stay inside ``root``; else None."""
    try:
        resolved = require_under(root, path)
        require_under(root, contained_path(resolved, "SKILL.md"))
    except (OSError, ValueError, PathTraversalError):
        return None
    if not is_under_root(resolved, root):
        return None
    if not is_pack_file(resolved, "SKILL.md"):
        return None
    return resolved


def catalog_entries(root: Path, *, include_agents: bool = False) -> list[dict[str, Any]]:
    """Skills in this project.

    Agent folders stay out unless ``include_agents`` is set. Evaluate uses
    that flag. A workspace copy wins when the slug matches.
    """
    root = root.expanduser().resolve()
    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()
    names_seen: set[str] = set()

    def add(path: Path, source: str) -> None:
        if source == "workspace":
            resolved = _workspace_skill_dir(path, root)
            if resolved is None:
                return
        else:
            resolved = path.resolve()
        if resolved in seen:
            return
        if not is_pack_file(resolved, "SKILL.md"):
            return
        seen.add(resolved)
        slug = folder_slug(resolved)
        loaded = ingest_skill(resolved, strict=False)
        slug = loaded.name or slug
        display = loaded.display_name or resolved.name
        skill_id = slug if slug not in names_seen else f"{source}:{slug}"
        names_seen.add(slug)
        entries.append(
            {
                "id": skill_id,
                "name": display,
                "slug": slug,
                "description": loaded.description,
                "warning": loaded.warning,
                "path": _display_path(resolved, root),
                "absolute": str(resolved),
                "source": source,
                "source_label": SOURCE_LABELS.get(source, source),
                "seed": slug == "pdf",
                "sabotaged": slug == "pdf-sabotaged",
            }
        )

    import os

    if is_skill_pack(root) or is_pack_file(root, "SKILL.md"):
        add(root, "workspace")
    skills_root = workspace_skills_root(root)
    if not os.path.isdir(os.fsdecode(skills_root)):
        for child in _iter_skill_dirs(root):
            add(child, "workspace")
    for child in _iter_skill_dirs(skills_root):
        add(child, "workspace")
    if include_agents:
        for source, getter in SOURCE_ROOTS:
            if getter is None:
                continue
            try:
                parent = getter()
            except OSError:
                continue
            for child in _iter_skill_dirs(parent):
                loaded = ingest_skill(child, strict=False)
                slug = loaded.name or folder_slug(child)
                if slug in names_seen:
                    continue
                add(child, source)
    return entries


def _immediate_agent_skill(path: Path) -> bool:
    """True when ``path`` is a direct child of a Cursor, Codex, or Claude skills folder."""
    from skillgate_ai.contained_fs import isdir_at, isfile_at

    resolved = path.expanduser().resolve()
    parent = resolved.parent
    for _source, getter in SOURCE_ROOTS:
        if getter is None:
            continue
        try:
            root = getter().resolve()
        except OSError:
            continue
        if parent != root:
            continue
        name = resolved.name
        return isdir_at(root, name) and isfile_at(root, name, "SKILL.md")
    return False


def safe_skill_folder_name(name: str) -> str:
    """Folder slug for ``skills/<name>/``. Display names are slugified; path escape is rejected."""
    text = (name or "").strip()
    if not text or text in {".", ".."} or "/" in text or "\\" in text:
        raise SkillGateError(
            "Skill names are lowercase letters, numbers, and hyphens.",
            hint="Example: pdf-tools",
        )
    if ".." in text.split("/"):
        raise SkillGateError(
            "Skill names are lowercase letters, numbers, and hyphens.",
            hint="Example: pdf-tools",
        )
    if NAME_RE.match(text):
        return text
    slug = folder_slug(Path(text))
    if not NAME_RE.match(slug):
        raise SkillGateError(
            "Skill names are lowercase letters, numbers, and hyphens.",
            hint="Example: pdf-tools",
        )
    return slug


def find_skill(root: Path, name: str) -> Path:
    text = (name or "").strip()
    if not text:
        raise SkillGateError("A skill name is required.")
    looks_like_path = text.startswith("/") or "/" in text or "\\" in text or ".." in text
    if looks_like_path:
        normalized = text.replace("\\", "/")
        is_absolute_path = normalized.startswith("/") or (
            len(normalized) > 1 and normalized[1] == ":"
        )
        if is_absolute_path:
            try:
                resolved = require_under(root, text)
            except PathTraversalError as exc:
                from skillgate_ai.paths import skill_pack_root

                try:
                    agent_path = skill_pack_root(text)
                except PathTraversalError:
                    raise SkillGateError("That path is outside this project.") from exc
                if _immediate_agent_skill(agent_path):
                    return agent_path
                raise SkillGateError("That path is outside this project.") from exc
        else:
            normalized = text.replace("\\", "/")
            parts = [piece for piece in normalized.split("/") if piece and piece != "."]
            if any(piece == ".." for piece in parts):
                raise SkillGateError("That path is outside this project.")
            try:
                resolved = contained_path(root, *parts)
            except PathTraversalError as exc:
                raise SkillGateError("That path is outside this project.") from exc
        if _immediate_agent_skill(resolved):
            return resolved
        if not is_under_root(resolved, root):
            raise SkillGateError("That path is outside this project.")
        contained = _workspace_skill_dir(resolved, root)
        if contained is not None:
            return contained
    if NAME_RE.match(text):
        contained = _workspace_skill_dir(workspace_skills_root(root) / text, root)
        if contained is not None:
            return contained
    for entry in catalog_entries(root, include_agents=True):
        if (
            entry["name"] == text
            or entry["id"] == text
            or entry.get("slug") == text
            or entry["absolute"] == text
        ):
            return Path(entry["absolute"])
    raise SkillGateError(
        f"Skill {text!r} was not found.",
        hint="Connect an agent, or paste a SKILL.md.",
    )


def import_from_agent_folders(
    root: Path, *, sources: list[str] | None = None, only: list[str] | None = None
) -> dict[str, Any]:
    """Copy chosen agent skill folders into ``<root>/skills/``. Skip names that already exist."""
    wanted = [item.strip().lower() for item in (sources or []) if item]
    if not wanted:
        raise SkillGateError(
            "Choose an agent first.",
            hint="Pick an agent, then import.",
        )
    slugs = {item.strip() for item in (only or []) if str(item).strip()}
    dest_parent = workspace_skills_root(root)
    dest_parent.mkdir(parents=True, exist_ok=True)
    imported: list[dict[str, str | None]] = []
    skipped: list[dict[str, str]] = []
    for source in wanted:
        if source == "workspace":
            continue
        parent = source_dir(source, root=root)
        for skill_dir in _iter_skill_dirs(parent):
            slug = folder_slug(skill_dir)
            if slugs and slug not in slugs and skill_dir.name not in slugs:
                continue
            dest = contained_path(dest_parent, slug)
            if dest.exists():
                skipped.append(
                    {
                        "name": skill_dir.name,
                        "slug": slug,
                        "source": source,
                        "reason": "already here",
                    }
                )
                continue
            try:
                copy_pack(skill_dir, dest, include_goldens=True)
            except (OSError, ValueError) as exc:
                skipped.append(
                    {
                        "name": skill_dir.name,
                        "source": source,
                        "reason": "Couldn't copy this skill.",
                    }
                )
                del exc
                if dest.exists() and dest != skill_dir:
                    try:
                        import shutil

                        shutil.rmtree(dest)
                    except OSError:
                        pass
                continue
            loaded = ingest_skill(dest, strict=False)
            imported.append(
                {
                    "name": loaded.display_name or dest.name,
                    "slug": loaded.name or dest.name,
                    "source": source,
                    "warning": loaded.warning,
                }
            )
    return {
        "imported": imported,
        "skipped": skipped,
        "skills": catalog_entries(root),
        "sources": agent_source_status(),
    }


def agent_source_status() -> list[dict[str, Any]]:
    """Per-agent connect status: folder found + skill counts. No filesystem paths."""
    rows: list[dict[str, Any]] = []
    for source, getter in SOURCE_ROOTS:
        if source == "workspace" or getter is None:
            continue
        label = SOURCE_LABELS.get(source, source)
        found = False
        count = 0
        try:
            parent = getter()
            found = parent.is_dir()
            if found:
                count = len(_iter_skill_dirs(parent))
        except OSError:
            found = False
        rows.append(
            {
                "id": source,
                "label": label,
                "found": found,
                "count": count,
                "folder_label": f"{label}'s skills folder",
            }
        )
    return rows


def _display_path(path: Path, root: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.name
    text = str(rel).replace("\\", "/")
    if text in {"", "."}:
        return path.name
    return text
