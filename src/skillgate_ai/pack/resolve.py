"""Read and write eval packs on disk."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.pack.pathsafe import _path_under_skill


def _inside_other_skill(path: Path, skill_root: Path) -> bool:
    resolved = path.resolve()
    root = skill_root.resolve()
    try:
        resolved.relative_to(root)
        return False
    except ValueError:
        pass
    for parent in resolved.parents:
        if parent == root:
            return False
        if (parent / "SKILL.md").is_file():
            return True
    return False


def _accept_input_file(candidate: Path | None, skill_root: Path | None) -> Path | None:
    if candidate is None or not candidate.is_file():
        return None
    if skill_root is not None and _inside_other_skill(candidate, skill_root):
        return None
    return candidate


def resolve_input_file(
    rel: str,
    *,
    skill_root: Path | None = None,
    root: Path | None = None,
    suite_dir: Path | None = None,
) -> Path | None:
    """Skill-root first (agentskills), then project/suite (bundled pdf templates)."""
    raw = (rel or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute() and path.is_file():
        accepted = _accept_input_file(path, skill_root)
        if accepted is not None:
            return accepted
    if skill_root is not None:
        candidate = _path_under_skill(skill_root, raw)
        accepted = _accept_input_file(candidate, skill_root)
        if accepted is not None:
            return accepted
    if root is None:
        return None
    suite = suite_dir or root / "evals"
    for base in (root, suite, suite.parent):
        candidate = (base / path).resolve()
        accepted = _accept_input_file(candidate, skill_root)
        if accepted is not None:
            return accepted
    return _accept_input_file((root / path).resolve(), skill_root)


def file_copy_from_rel(rel: str) -> dict[str, str]:
    cleaned = rel.replace("\\", "/").lstrip("/")
    return {"src": cleaned, "dest": Path(cleaned).name}
