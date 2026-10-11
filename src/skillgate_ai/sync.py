"""Sync skills from a git repo into local agent skills directories.

Optional add-on for the OSS CLI (no Skill Gate account). Clones a repo, copies
its ``skills/<name>/`` folders into the Cursor / Codex / Claude skills roots
(only the skill dirs it manages — unmanaged skills are never deleted).
"""

from __future__ import annotations

import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from skillgate_ai.deploy import adapters
from skillgate_ai.errors import SkillGateError
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.pack import copy_skill_pack

DEFAULT_TARGETS = ("cursor", "codex", "claude")
SYNC_STATE_FILE = ".skillgate-sync.json"
LAUNCH_AGENT_LABEL = "com.skillgate-ai.sync"


def target_roots() -> dict[str, Path]:
    """Resolved skills root per target id."""
    return {adapter.id: adapter.skills_root() for adapter in adapters()}


def default_targets() -> list[str]:
    return list(DEFAULT_TARGETS)


def normalize_targets(targets: list[str] | tuple[str, ...]) -> list[str]:
    known = set(target_roots())
    out: list[str] = []
    for target in targets:
        key = (target or "").strip().lower()
        if key in known and key not in out:
            out.append(key)
    return out


def _clone(repo_url: str, work: Path) -> None:
    proc = subprocess.run(
        ["git", "clone", "--depth", "1", repo_url, str(work)],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        hint = _redact(proc.stderr)
        raise SkillGateError(f"Could not clone the skills repo: {repo_url}", hint=hint or None)


def _redact(stderr: str) -> str:
    lines = [line for line in stderr.splitlines() if line.strip() and "fatal:" not in line]
    return "\n".join(lines[-5:]).strip()


def _reject_symlinks(skill_dir: Path) -> None:
    """Refuse to sync a skill that contains symlinks (a cloned repo is untrusted)."""
    if skill_dir.is_symlink():
        raise SkillGateError(
            f"Skill '{skill_dir.name}' is a symlink. Symlinks are not allowed in synced skills."
        )
    for root, dirs, files in os.walk(skill_dir, followlinks=False):
        for name in dirs + files:
            entry = Path(root) / name
            if entry.is_symlink():
                rel = entry.relative_to(skill_dir)
                raise SkillGateError(
                    f"Skill '{skill_dir.name}' contains a symlink ({rel.as_posix()}). "
                    "Symlinks are not allowed in synced skills."
                )


def _skill_names(repo_root: Path, path_prefix: str) -> list[str]:
    prefix = (path_prefix or "skills").strip().strip("/") or "skills"
    skills_dir = repo_root / prefix
    if not skills_dir.is_dir():
        return []
    return sorted(
        child.name
        for child in skills_dir.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    )


def _load_state(root: Path) -> list[str]:
    state = root / SYNC_STATE_FILE
    if not state.is_file():
        return []
    try:
        data = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if isinstance(data, dict):
        managed = data.get("skills")
        if isinstance(managed, list):
            return [str(name) for name in managed]
    return []


def _save_state(root: Path, names: list[str]) -> None:
    state = root / SYNC_STATE_FILE
    state.write_text(json.dumps({"skills": names}, indent=2), encoding="utf-8")


def _sync_one_target(
    *,
    root: Path,
    repo_root: Path,
    path_prefix: str,
    names: list[str],
) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    managed_before = {name for name in _load_state(root) if name}
    managed_after = set(names)
    for name in sorted(managed_before - managed_after):
        entry = root / name
        if entry.is_symlink():
            entry.unlink(missing_ok=True)
            continue
        if entry.is_dir() and entry.resolve().parent == root.resolve():
            shutil.rmtree(entry, ignore_errors=True)
    installed = 0
    for name in names:
        source = repo_root / (path_prefix or "skills") / name
        if not source.is_dir() or not (source / "SKILL.md").is_file():
            continue
        copy_skill_pack(source, root / name)
        ingest_skill(root / name)
        installed += 1
    _save_state(root, sorted(managed_after))
    return {
        "target_root": str(root),
        "installed": installed,
        "removed": len(managed_before - managed_after),
    }


def sync_once(
    repo_url: str,
    *,
    targets: list[str] | tuple[str, ...] | None = None,
    path_prefix: str = "skills",
) -> dict:
    """Clone the repo once and sync each managed skill into each target root."""
    selected = normalize_targets(list(targets) if targets else default_targets())
    if not selected:
        raise SkillGateError("Pick at least one of cursor, codex, or claude.")
    with tempfile.TemporaryDirectory(prefix="sg-sync-") as td:
        work = Path(td)
        _clone(repo_url, work)
        skills_dir = work / (path_prefix or "skills")
        if not skills_dir.is_dir():
            raise SkillGateError(
                f"That repo has no '{path_prefix or 'skills'}/' folder. Nothing was changed."
            )
        names = _skill_names(work, path_prefix)
        for name in names:
            _reject_symlinks(work / (path_prefix or "skills") / name)
        roots = target_roots()
        per_target = {
            target: _sync_one_target(
                root=roots[target], repo_root=work, path_prefix=path_prefix, names=names
            )
            for target in selected
        }
    return {"skills": names, "targets": per_target}


def run_sync_loop(
    repo_url: str,
    *,
    targets: list[str] | tuple[str, ...] | None = None,
    interval: int = 0,
) -> None:
    """Sync repeatedly; interval<=0 means once."""
    selected = normalize_targets(list(targets) if targets else default_targets())
    if not selected:
        raise SkillGateError("Pick at least one of cursor, codex, or claude.")
    while True:
        sync_once(repo_url, targets=selected)
        if interval <= 0:
            return
        time.sleep(max(1, interval))


def launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def install_launchd_plist(
    repo_url: str,
    *,
    targets: list[str] | tuple[str, ...] | None = None,
    interval: int = 0,
) -> Path:
    """Write a macOS LaunchAgent that runs ``skillgate sync`` hands-off."""
    if sys.platform != "darwin":
        raise SkillGateError("LaunchAgent autostart is macOS-only.")
    selected = normalize_targets(list(targets) if targets else default_targets())
    if not repo_url or not repo_url.strip():
        raise SkillGateError("A skills repo URL is required for sync autostart.")
    binary = shutil.which("skillgate") or "skillgate"
    program = [binary, "sync", "--repo", repo_url.strip()]
    if selected:
        program += ["--targets", ",".join(selected)]
    if interval > 0:
        program += ["--interval", str(interval)]
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "RunAtLoad": True,
        "ProgramArguments": program,
    }
    launch_dir = launch_agents_dir()
    launch_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(launch_dir, 0o755)
    except OSError:
        pass
    dest = launch_dir / f"{LAUNCH_AGENT_LABEL}.plist"
    with open(dest, "wb") as handle:
        plistlib.dump(plist, handle)
    os.chmod(dest, 0o644)
    return dest