"""Skill catalog: project ``skills/`` plus Cursor / Codex / Claude folders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skillgate_ai.deploy import claude_skills_root, codex_skills_root, cursor_skills_root
from skillgate_ai.errors import SkillGateError
from skillgate_ai.ingest import NAME_RE, folder_slug, ingest_skill
from skillgate_ai.pack import copy_skill_pack as copy_pack
from skillgate_ai.paths import is_skill_pack, is_under_root

SOURCE_ROOTS = (
    ("workspace", None),
    ("cursor", cursor_skills_root),
    ("codex", codex_skills_root),
    ("claude", claude_skills_root),
)

SOURCE_LABELS = {
    "workspace": "this project",
    "cursor": "Cursor",
    "codex": "Codex",
    "claude": "Claude",
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
    raise SkillGateError("Import source must be Cursor, Codex, Claude, or this project.")


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


def catalog_entries(root: Path) -> list[dict[str, Any]]:
    """Skills in this project only. Agent folders are a Connect source, not the list."""
    root = root.expanduser().resolve()
    entries: list[dict[str, Any]] = []
    seen: set[Path] = set()
    names_seen: set[str] = set()

    def add(path: Path, source: str) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        if not (resolved / "SKILL.md").is_file():
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

    if is_skill_pack(root) or (root / "SKILL.md").is_file():
        add(root, "workspace")
    skills_root = workspace_skills_root(root)
    if not skills_root.is_dir():
        for child in _iter_skill_dirs(root):
            add(child, "workspace")
    for child in _iter_skill_dirs(skills_root):
        add(child, "workspace")
    return entries


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
    supplied = Path(text).expanduser()
    looks_like_path = supplied.is_absolute() or "/" in text or "\\" in text or ".." in text
    if looks_like_path:
        resolved = supplied.resolve() if supplied.is_absolute() else (root / text).resolve()
        if not is_under_root(resolved, root):
            raise SkillGateError("That path is outside this project.")
        if (resolved / "SKILL.md").is_file():
            return resolved
    if NAME_RE.match(text):
        workspace = workspace_skills_root(root) / text
        if (workspace / "SKILL.md").is_file():
            return workspace.resolve()
    for entry in catalog_entries(root):
        if (
            entry["name"] == text
            or entry["id"] == text
            or entry.get("slug") == text
            or entry["absolute"] == text
        ):
            return Path(entry["absolute"])
    raise SkillGateError(
        f"Skill {text!r} was not found.",
        hint="Connect Cursor, Codex, or Claude, or paste a SKILL.md.",
    )


def import_from_agent_folders(
    root: Path, *, sources: list[str] | None = None, only: list[str] | None = None
) -> dict[str, Any]:
    """Copy chosen agent skill folders into ``<root>/skills/``. Skip names that already exist."""
    wanted = [item.strip().lower() for item in (sources or []) if item]
    if not wanted:
        raise SkillGateError(
            "Choose Cursor, Codex, or Claude first.",
            hint="Pick an agent, then import.",
        )
    slugs = {item.strip() for item in (only or []) if str(item).strip()}
    dest_parent = workspace_skills_root(root)
    dest_parent.mkdir(parents=True, exist_ok=True)
    imported: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for source in wanted:
        if source == "workspace":
            continue
        parent = source_dir(source, root=root)
        for skill_dir in _iter_skill_dirs(parent):
            slug = folder_slug(skill_dir)
            if slugs and slug not in slugs and skill_dir.name not in slugs:
                continue
            dest = dest_parent / slug
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
