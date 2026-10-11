"""Write SKILL.md frontmatter + body, then ingest to validate."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from skillgate_ai.ingest import Skill, ingest_skill

DEFAULT_BODY = """# {name}

## When to use

Use this skill when the user's request matches the description.

## How to work

Prefer bundled scripts under `scripts/` if they exist.
"""

DEFAULT_DESCRIPTION = (
    "Help with {name} tasks in this workspace. "
    "Use when the user asks for {name} or wants the documented {name} workflow."
)


def default_description(name: str) -> str:
    return DEFAULT_DESCRIPTION.format(name=name)


def default_body(name: str) -> str:
    return DEFAULT_BODY.format(name=name)


def write_skill_md(
    folder: str | Path,
    *,
    name: str,
    description: str,
    body: str = "",
    license: str | None = None,
    compatibility: str | None = None,
    allowed_tools: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> Skill:
    """Write SKILL.md and return the ingested skill (raises IngestError)."""
    dest = Path(folder).expanduser()
    dest.mkdir(parents=True, exist_ok=True)
    parsed: dict[str, Any] = {
        "name": name,
        "description": description,
    }
    if license:
        parsed["license"] = license
    if compatibility:
        parsed["compatibility"] = compatibility
    if allowed_tools:
        parsed["allowed-tools"] = allowed_tools
    if metadata:
        parsed["metadata"] = metadata
    dumped = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True)
    text = body if body else default_body(name)
    if text and not text.endswith("\n"):
        text += "\n"
    (dest / "SKILL.md").write_text(f"---\n{dumped}---\n{text}", encoding="utf-8")
    return ingest_skill(dest)


def skill_to_dict(skill: Skill) -> dict[str, Any]:
    return {
        "path": str(skill.path),
        "name": skill.name,
        "description": skill.description,
        "body": skill.body,
        "license": skill.license,
        "compatibility": skill.compatibility,
        "allowed_tools": skill.allowed_tools,
        "metadata": dict(skill.metadata),
    }
