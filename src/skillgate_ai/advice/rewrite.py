from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from skillgate_ai.ingest import FRONTMATTER_RE


def rewrite_skill_description(skill_md: Path, new_description: str) -> None:
    text = skill_md.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("SKILL.md has no YAML frontmatter to patch.")
    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        raise ValueError("SKILL.md frontmatter is not a mapping.")
    parsed["description"] = new_description
    body = text[match.end() :]
    dumped = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True)
    skill_md.write_text(f"---\n{dumped}---\n{body}", encoding="utf-8")


def description_from_paste(markdown: str) -> str:
    text = (markdown or "").strip()
    if text and not text.endswith("\n"):
        text += "\n"
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("Paste a SKILL.md frontmatter block with a description.")
    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        raise ValueError("Paste a SKILL.md frontmatter block with a description.")
    desc = str(parsed.get("description") or "").strip()
    if not desc:
        raise ValueError("The pasted frontmatter has no description.")
    return desc


def apply_description_fix(
    *,
    source: Path,
    dest_root: Path,
    new_description: str,
    restore_scripts_from: Path | None = None,
) -> Path:
    """Copy the skill to a working folder, write the corrected description, keep the same name."""
    dest = dest_root / source.name
    source = source.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.resolve() == source:
        rewrite_skill_description(dest / "SKILL.md", new_description)
    else:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source, dest)
        rewrite_skill_description(dest / "SKILL.md", new_description)
    if restore_scripts_from and restore_scripts_from.is_dir():
        src_scripts = restore_scripts_from / "scripts"
        if src_scripts.is_dir():
            dest_scripts = dest / "scripts"
            if dest_scripts.exists():
                shutil.rmtree(dest_scripts)
            shutil.copytree(src_scripts, dest_scripts)
    return dest
