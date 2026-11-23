"""Read and write eval packs on disk."""

from __future__ import annotations

import re
from pathlib import Path

from skillgate_ai.errors import SkillGateError
from skillgate_ai.pack.constants import _SAFE_NAME, FIXTURE_DIR
from skillgate_ai.pack.pathsafe import (
    _safe_filename,
    fixture_src_for,
    implied_fixture_name,
    safe_relpath,
)
from skillgate_ai.pack.resolve import resolve_input_file
from skillgate_ai.pack.samples import (
    CannotSynthesizeFixture,
    cannot_synthesize_sample,
    generate_sample_bytes,
)


def write_pack_file(
    skill_path: str | Path,
    *,
    rel: str,
    content: str | bytes,
) -> dict[str, str]:
    """Write bytes into the skill directory. Returns src (skill-relative) + dest."""
    root = Path(skill_path).expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Skill folder not found.")
    try:
        relative = safe_relpath(rel)
        dest_path = (root / relative).resolve()
        dest_path.relative_to(root)
    except ValueError as exc:
        raise SkillGateError(
            "That path is outside the skill folder.",
            hint="Pick a file inside this skill.",
        ) from exc
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8") if isinstance(content, str) else content
    from skillgate_ai.pack_schema import guard_cases_yaml_write

    guard_cases_yaml_write(root, relative, data)
    dest_path.write_bytes(data)
    return {"src": relative, "dest": Path(relative).name, "path": relative}


def write_sample_fixture(
    skill_path: str | Path,
    *,
    dest: str | None = None,
    prompt: str = "",
    description: str = "",
) -> dict[str, str]:
    """Create a synthetic fixture under evals/fixtures/. Never invent a photo/scan."""
    if cannot_synthesize_sample(dest=dest or "", prompt=prompt, description=description):
        raise CannotSynthesizeFixture()
    name = dest or implied_fixture_name(f"{prompt} {description}")
    cleaned = name.replace("\\", "/").lstrip("/")
    if Path(cleaned).name.lower() == "skill.md":
        raise SkillGateError(
            "SKILL.md is the skill, not a fixture.",
            hint="Pass a path under evals/fixtures/.",
        )
    if "/" in name:  # noqa: SIM108
        relative = safe_relpath(name)
    else:
        relative = safe_relpath(f"{FIXTURE_DIR}/{name}")
    payload = generate_sample_bytes(dest=relative, prompt=prompt or description)
    return write_pack_file(skill_path, rel=relative, content=payload)


def copy_into_pack(
    skill_path: str | Path,
    *,
    src: str | Path,
    dest_name: str | None = None,
) -> dict[str, str]:
    """Copy an existing file into evals/fixtures/ (promote / attach)."""
    source = Path(src)
    if not source.is_file():
        raise FileNotFoundError(str(src))
    name = Path(dest_name or source.name).name
    return write_pack_file(skill_path, rel=f"{FIXTURE_DIR}/{name}", content=source.read_bytes())


def promote_file_into_pack(
    skill_path: str | Path,
    *,
    src: str,
    dest: str = "",
    root: Path | None = None,
) -> dict[str, str]:
    """Copy or rewrite so files[].src is always relative to the skill pack root."""
    skill_root = Path(skill_path).expanduser().resolve()
    dest_name = Path(dest or src).name or "sample.bin"
    dest_name = _safe_filename(dest_name)
    rewritten = {"src": fixture_src_for(src, dest_name), "dest": dest_name}
    if not (src or "").strip():
        return rewritten
    resolved = resolve_input_file(src, skill_root=skill_root, root=root)
    if resolved is None or not resolved.is_file():
        return rewritten
    try:
        rel = resolved.resolve().relative_to(skill_root).as_posix()
        return {"src": rel, "dest": dest_name or Path(rel).name}
    except ValueError:
        pass
    try:
        return copy_into_pack(skill_root, src=resolved, dest_name=dest_name)
    except (OSError, ValueError, FileNotFoundError):
        return rewritten


def persist_case_file(
    skill_path: str | Path,
    *,
    text: str,
    check_id: str = "case",
    index: int = 1,
) -> dict[str, str]:
    """Save prompt/facts into evals/fixtures/ so the pack stays the only copy."""
    body = (text or "").strip()
    if not body:
        raise ValueError("Nothing to save into the skill folder.")
    slug = _SAFE_NAME.sub("-", check_id).strip("-").lower() or "case"
    if slug.startswith("regression"):
        name = f"{slug}.md"
    elif re.search(r"\b(standup|yesterday|blockers?)\b", body, re.IGNORECASE):
        name = f"standup-case-{index}.md"
    else:
        name = f"{slug}.md" if slug not in {"should-trigger-1", "case"} else f"case-{index}.md"
    content = body if body.endswith("\n") else body + "\n"
    return write_pack_file(skill_path, rel=f"{FIXTURE_DIR}/{name}", content=content)
