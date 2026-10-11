"""Strict agentskills / SKILL.md ingest."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from skillgate_ai.errors import IngestError

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---[ \t]*\n(.*?\n)---[ \t]*(?:\n|$)", re.DOTALL)
# Dockerfile CMD is `check /pack`; Compose bind-mounts the skill at that path.
# The agentskills name==folder rule still applies to the source pack on disk.
_GENERIC_MOUNT_NAMES = frozenset({"pack"})
OPTIONAL_STRING_FIELDS = ("license", "compatibility", "allowed-tools")
KNOWN_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}


@dataclass
class Skill:
    path: Path
    name: str
    description: str
    body: str
    license: str | None = None
    compatibility: str | None = None
    allowed_tools: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
    extra_frontmatter: dict[str, Any] = field(default_factory=dict)
    display_name: str = ""
    warning: str | None = None

    def __post_init__(self) -> None:
        if not self.display_name:
            self.display_name = self.name

    @property
    def skill_md(self) -> Path:
        return self.path / "SKILL.md"


def folder_slug(folder: Path) -> str:
    """Stable id from the folder name. Display names live in frontmatter."""
    name = folder.name.strip()
    if NAME_RE.match(name):
        return name
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "skill"


def ingest_skill(path: str | Path, *, strict: bool = True) -> Skill:
    folder = Path(path).expanduser().resolve()
    if not strict:
        return _ingest_lenient(folder)
    if not folder.exists():
        raise IngestError(f"Skill folder not found: {folder}")
    if not folder.is_dir():
        raise IngestError(f"Skill path is not a directory: {folder}")
    skill_md = folder / "SKILL.md"
    if not skill_md.is_file():
        raise IngestError(
            f"Missing SKILL.md in {folder.name}/",
            hint="A skill is a folder with a SKILL.md file (agentskills spec).",
        )
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise IngestError(
            f"{folder.name}/SKILL.md must start with YAML frontmatter delimited by ---",
            hint="First line should be --- then name/description, then --- again.",
        )
    raw_fm = match.group(1)
    body = text[match.end() :]
    try:
        parsed = yaml.safe_load(raw_fm) or {}
    except yaml.YAMLError as exc:
        raise IngestError(f"{folder.name}/SKILL.md frontmatter is not valid YAML: {exc}") from exc
    if not isinstance(parsed, dict):
        raise IngestError(f"{folder.name}/SKILL.md frontmatter must be a mapping of fields")

    name = _require_name(parsed.get("name"), folder)
    description = _require_description(parsed.get("description"), folder)
    clean_meta, extra, compatibility = _frontmatter_extras(parsed, folder, strict=True)

    return Skill(
        path=folder,
        name=name,
        display_name=name,
        description=description,
        body=body,
        license=_opt_str(parsed.get("license")),
        compatibility=_opt_str(compatibility),
        allowed_tools=_opt_str(parsed.get("allowed-tools")),
        metadata=clean_meta,
        extra_frontmatter=extra,
    )


def ingest_skills(paths: list[str | Path], *, strict: bool = True) -> list[Skill]:
    skills = [ingest_skill(p, strict=strict) for p in paths]
    names = [s.name for s in skills]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        raise IngestError(f"Duplicate skill names: {', '.join(sorted(dupes))}")
    return skills


def discover_skills(skills_root: str | Path) -> list[Skill]:
    root = Path(skills_root)
    if not root.is_dir():
        raise IngestError(f"skills/ folder not found: {root}")
    found: list[Skill] = []
    errors: list[str] = []
    for child in sorted(root.iterdir()):
        if child.is_dir() and (child / "SKILL.md").exists():
            try:
                found.append(ingest_skill(child))
            except IngestError as exc:
                errors.append(exc.message)
    if not found:
        if errors:
            raise IngestError("No valid skills in skills/", hint="\n".join(errors))
        raise IngestError(
            "No SKILL.md folders in skills/",
            hint="Bundled seeds should live at $SKILLGATE_ROOT/skills, or pass a pack to `skillgate check`.",
        )
    return found


def _ingest_lenient(folder: Path) -> Skill:
    """List and run real-world skills. Slug is the folder; keep the display name.

    Never raises. Broken SKILL.md is listed with a friendly warning.
    """
    slug = folder_slug(folder) if folder.name else "skill"
    if not folder.exists() or not folder.is_dir():
        return Skill(
            path=folder,
            name=slug,
            display_name=folder.name or slug,
            description="",
            body="",
            warning="This skill folder is missing.",
        )
    skill_md = folder / "SKILL.md"
    if not skill_md.is_file():
        return Skill(
            path=folder,
            name=slug,
            display_name=folder.name,
            description="",
            body="",
            warning="This skill is missing its SKILL.md file.",
        )
    try:
        text = skill_md.read_text(encoding="utf-8")
    except OSError:
        return Skill(
            path=folder,
            name=slug,
            display_name=folder.name,
            description="",
            body="",
            warning="Couldn't read this skill’s details.",
        )
    match = FRONTMATTER_RE.match(text)
    if not match:
        return Skill(
            path=folder,
            name=slug,
            display_name=folder.name,
            description="",
            body=text,
            warning="This skill’s SKILL.md is missing its header.",
        )
    body = text[match.end() :]
    try:
        parsed = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return Skill(
            path=folder,
            name=slug,
            display_name=folder.name,
            description="",
            body=body,
            warning="Couldn't read this skill’s details.",
        )
    if not isinstance(parsed, dict):
        return Skill(
            path=folder,
            name=slug,
            display_name=folder.name,
            description="",
            body=body,
            warning="Couldn't read this skill’s details.",
        )
    raw_name = parsed.get("name")
    display = raw_name.strip() if isinstance(raw_name, str) and raw_name.strip() else folder.name
    description = ""
    warning = None
    raw_desc = parsed.get("description")
    if isinstance(raw_desc, str) and raw_desc.strip():
        description = raw_desc.strip()
        if len(description) > 1024:
            description = description[:1024]
            warning = "This skill’s description was truncated."
    elif raw_desc is None or (isinstance(raw_desc, str) and not raw_desc.strip()):
        warning = "This skill is missing a description."
    else:
        warning = "This skill is missing a description."
    try:
        clean_meta, extra, compatibility = _frontmatter_extras(parsed, folder, strict=False)
    except (TypeError, ValueError, IngestError):
        clean_meta, extra, compatibility = {}, {}, None
        warning = warning or "Couldn't read this skill’s details."
    return Skill(
        path=folder,
        name=slug,
        display_name=display,
        description=description,
        body=body,
        license=_opt_str(parsed.get("license")),
        compatibility=_opt_str(compatibility) if compatibility is not None else None,
        allowed_tools=_opt_str(parsed.get("allowed-tools")),
        metadata=clean_meta,
        extra_frontmatter=extra,
        warning=warning,
    )


def _frontmatter_extras(
    parsed: dict[str, Any], folder: Path, *, strict: bool
) -> tuple[dict[str, str], dict[str, Any], Any]:
    metadata = parsed.get("metadata") or {}
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, dict):
        if strict:
            raise IngestError(f"{folder.name}: metadata must be a map of string keys to string values")
        metadata = {}
    clean_meta: dict[str, str] = {}
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, (str, int, float, bool)):
            if strict:
                raise IngestError(f"{folder.name}: metadata values must be strings (key {key!r})")
            continue
        clean_meta[str(key)] = str(value)
    extra = {k: v for k, v in parsed.items() if k not in KNOWN_FIELDS}
    compatibility = parsed.get("compatibility")
    if compatibility is not None:
        if not isinstance(compatibility, str) or not (1 <= len(compatibility) <= 500):
            if strict:
                raise IngestError(f"{folder.name}: compatibility must be 1–500 characters if set")
            compatibility = None
    return clean_meta, extra, compatibility


def _require_name(value: Any, folder: Path) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IngestError(f"{folder.name}/SKILL.md is missing required frontmatter field `name`")
    name = value.strip()
    if not (1 <= len(name) <= 64):
        raise IngestError(f"{folder.name}: name must be 1–64 characters (got {len(name)})")
    if not NAME_RE.match(name):
        raise IngestError(
            f"{folder.name}: name {name!r} is invalid",
            hint="Use lowercase letters, numbers, and single hyphens; no leading/trailing/double hyphens.",
        )
    if name != folder.name and folder.name not in _GENERIC_MOUNT_NAMES:
        raise IngestError(
            f"Skill name {name!r} must match the folder name {folder.name!r}",
            hint="Rename the folder or the `name` field so they match.",
        )
    return name


def _require_description(value: Any, folder: Path) -> str:
    if isinstance(value, str):
        description = value.strip()
    elif value is None:
        description = ""
    else:
        raise IngestError(f"{folder.name}: description must be a string")
    if not description:
        raise IngestError(f"{folder.name}/SKILL.md is missing required frontmatter field `description`")
    if len(description) > 1024:
        raise IngestError(
            f"{folder.name}: description is {len(description)} characters (max 1024)"
        )
    return description


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
