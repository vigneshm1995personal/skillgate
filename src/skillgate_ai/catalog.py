"""Skill catalog: project ``skills/`` plus Cursor / Codex / Claude folders."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skillgate_ai.deploy import claude_skills_root, codex_skills_root, cursor_skills_root
from skillgate_ai.errors import SkillGateError
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.pack import copy_skill_pack as copy_pack
from skillgate_ai.paths import is_skill_pack

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
    """Workspace packs first, then agent skill folders. First name wins on lookup."""
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
        name = resolved.name
        skill_id = name if name not in names_seen else str(resolved)
        names_seen.add(name)
        try:
            loaded = ingest_skill(resolved)
            description = loaded.description
            name = loaded.name or name
        except SkillGateError:
            description = ""
        entries.append(
            {
                "id": skill_id,
                "name": name,
                "description": description,
                "path": _display_path(resolved, root),
                "absolute": str(resolved),
                "source": source,
                "source_label": SOURCE_LABELS.get(source, source),
                "seed": name == "pdf",
                "sabotaged": name == "pdf-sabotaged",
            }
        )

    if is_skill_pack(root) or (root / "SKILL.md").is_file():
        add(root, "workspace")
    for child in _iter_skill_dirs(workspace_skills_root(root)):
        add(child, "workspace")
    for source, getter in SOURCE_ROOTS:
        if source == "workspace" or getter is None:
            continue
        try:
            parent = getter()
        except OSError:
            continue
        for child in _iter_skill_dirs(parent):
            add(child, source)
    return entries


def find_skill(root: Path, name: str) -> Path:
    text = (name or "").strip()
    if not text:
        raise SkillGateError("A skill name is required.")
    supplied = Path(text).expanduser()
    if supplied.is_absolute() and (supplied / "SKILL.md").is_file():
        return supplied.resolve()
    for entry in catalog_entries(root):
        if entry["name"] == text or entry["id"] == text or entry["absolute"] == text:
            return Path(entry["absolute"])
    workspace = workspace_skills_root(root) / text
    if (workspace / "SKILL.md").is_file():
        return workspace.resolve()
    raise SkillGateError(
        f"Skill {text!r} was not found.",
        hint="Import from ~/.cursor/skills, ~/.codex/skills, or ~/.claude/skills, or open a folder with SKILL.md.",
    )


def import_from_agent_folders(
    root: Path, *, sources: list[str] | None = None
) -> dict[str, Any]:
    """Copy agent skill folders into ``<root>/skills/``. Skip names that already exist."""
    wanted = [item.strip().lower() for item in (sources or ["cursor", "codex", "claude"]) if item]
    dest_parent = workspace_skills_root(root)
    dest_parent.mkdir(parents=True, exist_ok=True)
    imported: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    for source in wanted:
        if source == "workspace":
            continue
        parent = source_dir(source, root=root)
        for skill_dir in _iter_skill_dirs(parent):
            dest = dest_parent / skill_dir.name
            if dest.exists():
                skipped.append({"name": skill_dir.name, "source": source, "reason": "already here"})
                continue
            try:
                copy_pack(skill_dir, dest)
                ingest_skill(dest)
            except (SkillGateError, OSError, ValueError) as exc:
                skipped.append({"name": skill_dir.name, "source": source, "reason": str(exc)})
                if dest.exists() and dest != skill_dir:
                    try:
                        import shutil

                        shutil.rmtree(dest)
                    except OSError:
                        pass
                continue
            imported.append({"name": skill_dir.name, "source": source, "dest": str(dest)})
    return {
        "imported": imported,
        "skipped": skipped,
        "skills": catalog_entries(root),
    }


def _display_path(path: Path, root: Path) -> str:
    try:
        rel = path.resolve().relative_to(root.resolve())
    except ValueError:
        return path.name
    text = str(rel).replace("\\", "/")
    if text in {"", "."}:
        return path.name
    return text
