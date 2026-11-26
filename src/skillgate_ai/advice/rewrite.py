from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from skillgate_ai.ingest import FRONTMATTER_RE
from skillgate_ai.pack.pathsafe import _path_under_skill, resolve_pack_root
from skillgate_ai.pack.tree import pack_file_path


def rewrite_skill_description(skill_md: Path, new_description: str) -> None:
    if skill_md.name != "SKILL.md":
        raise ValueError("Expected SKILL.md")
    try:
        skill_md = pack_file_path(skill_md.parent, "SKILL.md")
    except FileNotFoundError as exc:
        raise ValueError("SKILL.md not found in skill folder.") from exc
    from skillgate_ai.pack_io import read_pack_text, write_pack_text

    text = read_pack_text(skill_md.parent, "SKILL.md")
    match = FRONTMATTER_RE.match(text)
    if not match:
        raise ValueError("SKILL.md has no YAML frontmatter to patch.")
    parsed = yaml.safe_load(match.group(1)) or {}
    if not isinstance(parsed, dict):
        raise ValueError("SKILL.md frontmatter is not a mapping.")
    parsed["description"] = new_description
    body = text[match.end() :]
    dumped = yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True)
    write_pack_text(skill_md.parent, "SKILL.md", f"---\n{dumped}---\n{body}")


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
    source_dir = resolve_pack_root(source)
    dest_root = dest_root.expanduser().resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    dest = _path_under_skill(dest_root, source_dir.name)
    if dest is None:
        raise ValueError("Path must stay inside the working folder.")
    if dest.exists() and dest.resolve() == source_dir.resolve():
        rewrite_skill_description(dest / "SKILL.md", new_description)
    else:
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(source_dir, dest)
        rewrite_skill_description(dest / "SKILL.md", new_description)
    if restore_scripts_from and restore_scripts_from.is_dir():
        restore_scripts_from = resolve_pack_root(restore_scripts_from)
        src_scripts = restore_scripts_from / "scripts"
        if src_scripts.is_dir():
            dest_scripts = dest / "scripts"
            if dest_scripts.exists():
                shutil.rmtree(dest_scripts)
            shutil.copytree(src_scripts, dest_scripts)
    return dest
