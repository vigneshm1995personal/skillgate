"""Optional host tools referenced by skills (warn at ingest when missing)."""

from __future__ import annotations

import shutil
from pathlib import Path

from skillgate_ai.ingest import Skill

_TOOL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pandoc", ("pandoc",)),
    ("playwright", ("playwright", "npx playwright", "playwright install")),
    ("libreoffice", ("libreoffice", "soffice", "libreoffice --headless")),
)


def missing_tool_warnings(skill: Skill) -> list[str]:
    blob = " ".join(
        part
        for part in (
            skill.description,
            skill.body,
            skill.allowed_tools or "",
            _scripts_blob(skill.path),
        )
        if part
    ).lower()
    warnings: list[str] = []
    for label, needles in _TOOL_PATTERNS:
        if any(needle in blob for needle in needles):
            binary = needles[0].split()[0]
            if shutil.which(binary) is None:
                warnings.append(
                    f"This skill may need {label} on the host (`{binary}` was not found on PATH)."
                )
    return warnings


def _scripts_blob(skill_path: Path) -> str:
    scripts = skill_path / "scripts"
    if not scripts.is_dir():
        return ""
    parts: list[str] = []
    for path in scripts.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".py", ".sh", ".bash"}:
            try:
                parts.append(path.read_text(encoding="utf-8", errors="replace")[:8000])
            except OSError:
                continue
    return "\n".join(parts)
