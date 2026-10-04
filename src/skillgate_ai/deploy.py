"""Local install adapters: copy a gated skill pack into Cursor / Codex / Claude skills dirs."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import NotRequired, Protocol, TypedDict

from skillgate_ai.errors import DeployError, IngestError
from skillgate_ai.ingest import Skill, ingest_skill
from skillgate_ai.pack import copy_skill_pack


class DeployResult(TypedDict):
    target: str
    status: str
    dest_path: str | None
    message: str
    mode: NotRequired[str]
    pack_path: NotRequired[str | None]
    file_count: NotRequired[int | None]


class DeployAdapter(Protocol):
    id: str
    label: str
    live: bool

    def skills_root(self) -> Path:
        """Directory that will contain <name>/SKILL.md."""
        ...

    def install(self, *, skill: Skill, source: Path) -> DeployResult:
        """Copy source skill pack to skills_root / skill.name. Re-ingest dest."""
        ...


def _override_root(env_var: str) -> Path | None:
    env = os.environ.get(env_var, "").strip()
    return Path(env).expanduser().resolve() if env else None


def cursor_skills_root() -> Path:
    return _override_root("SKILLGATE_CURSOR_SKILLS") or (
        Path.home() / ".cursor" / "skills"
    ).resolve()


def codex_skills_root() -> Path:
    return _override_root("SKILLGATE_CODEX_SKILLS") or (
        Path.home() / ".codex" / "skills"
    ).resolve()


def claude_skills_root() -> Path:
    return _override_root("SKILLGATE_CLAUDE_SKILLS") or (
        Path.home() / ".claude" / "skills"
    ).resolve()


class _PackAdapter:
    id: str = ""
    label: str = ""
    live: bool = True

    def skills_root(self) -> Path:
        raise NotImplementedError

    def install(self, *, skill: Skill, source: Path) -> DeployResult:
        source = source.expanduser().resolve()
        name = (skill.name or "").strip()
        if not name:
            raise DeployError("Skill name is missing.")
        if source.name != name:
            raise DeployError(
                f"Skill folder {source.name!r} does not match name {name!r}.",
                hint="The gated folder must match the skill name.",
            )
        if not source.is_dir() or not (source / "SKILL.md").is_file():
            raise DeployError(
                "The gated skill folder is gone. Re-run `skillgate check`, then install.",
            )
        dest = (self.skills_root() / name).resolve()
        if source == dest:
            raise DeployError(
                f"Install source and {self.label} dest are the same folder — "
                "refusing to overwrite the only copy."
            )
        self.skills_root().mkdir(parents=True, exist_ok=True)
        try:
            copied = copy_skill_pack(source, dest)
            ingest_skill(dest)
        except IngestError as exc:
            if dest.exists():
                shutil.rmtree(dest)
            raise DeployError(exc.message, hint=exc.hint) from exc
        except ValueError as exc:
            if dest.exists() and dest != source:
                shutil.rmtree(dest)
            raise DeployError(str(exc)) from exc
        except OSError as exc:
            if dest.exists() and dest != source:
                shutil.rmtree(dest)
            raise DeployError(f"Could not copy the skill into {self.label}: {exc}") from exc
        file_count = int(copied["file_count"])
        return {
            "target": self.id,
            "status": "installed",
            "mode": "local",
            "dest_path": str(copied["dest_path"]),
            "pack_path": str(copied["pack_path"]),
            "file_count": file_count,
            "message": f"Installed {name} ({file_count} files) → {copied['dest_path']}",
        }


class CursorAdapter(_PackAdapter):
    id = "cursor"
    label = "Cursor"

    def skills_root(self) -> Path:
        return cursor_skills_root()


class ClaudeAdapter(_PackAdapter):
    id = "claude"
    label = "Claude"

    def skills_root(self) -> Path:
        return claude_skills_root()


class CodexAdapter(_PackAdapter):
    id = "codex"
    label = "Codex"

    def skills_root(self) -> Path:
        return codex_skills_root()


def install_to_cursor(*, skill: Skill, source: Path) -> DeployResult:
    return CursorAdapter().install(skill=skill, source=source)


ADAPTERS: dict[str, type] = {
    "cursor": CursorAdapter,
    "claude": ClaudeAdapter,
    "codex": CodexAdapter,
}


def adapters() -> list[DeployAdapter]:
    return [cls() for cls in ADAPTERS.values()]


def deploy_targets() -> list[str]:
    return list(ADAPTERS)


def live_targets() -> list[str]:
    return [adapter.id for adapter in adapters() if adapter.live]


def deploy_roots() -> dict[str, str]:
    return {adapter.id: str(adapter.skills_root()) for adapter in adapters()}


def get_adapter(target: str) -> DeployAdapter:
    key = (target or "").strip().lower()
    cls = ADAPTERS.get(key)
    if cls is None:
        raise DeployError("Deploy target must be Cursor, Claude, or Codex.")
    return cls()


def local_deploy_available() -> bool:
    return True


def deploy_status() -> dict[str, object]:
    return {
        "platforms": deploy_targets(),
        "live": live_targets(),
        "roots": deploy_roots(),
        "modes": ["local"],
        "local_available": True,
    }
