"""MCP tool context: project root and shared run registry."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skillgate_ai.catalog import find_skill
from skillgate_ai.errors import SkillGateError
from skillgate_ai.run_registry import RunRegistry


@dataclass
class McpContext:
    root: Path
    registry: RunRegistry
    run_meta: dict[str, dict[str, Any]] = field(default_factory=dict)

    @classmethod
    def for_root(cls, root: Path) -> McpContext:
        root = root.expanduser().resolve()
        return cls(root=root, registry=RunRegistry(root))


def resolve_pack(ctx: McpContext, skill: str) -> Path:
    """Accept a pack dir, a skill name/slug, or a path to SKILL.md."""
    text = str(skill or "").strip()
    if not text:
        raise SkillGateError("A skill name is required.")
    if Path(text).name == "SKILL.md":
        text = str(Path(text).parent)
    return find_skill(ctx.root, text)


def tool_error_payload(exc: SkillGateError) -> dict[str, Any]:
    out: dict[str, Any] = {"message": exc.message}
    if exc.hint:
        out["hint"] = exc.hint
    return out
