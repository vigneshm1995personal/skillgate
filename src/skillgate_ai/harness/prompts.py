"""Agent harnesses: Cursor Agent, Codex CLI, and Claude Code in the sandbox workspace."""

from __future__ import annotations

import os
from pathlib import Path

import skillgate_ai.harness.bins as bins
import skillgate_ai.harness.selection as selection
from skillgate_ai.harness.selection import _MISSING
from skillgate_ai.ingest import Skill


def _workspace_trigger_mode(workspace: Path) -> bool:
    marker = workspace / ".skillgate" / "mode"
    if not marker.is_file():
        return False
    return marker.read_text(encoding="utf-8").strip() == "trigger"


def _trigger_mode_prompt(task: str) -> str:
    """Install is on disk. The prompt does not name a skill."""
    return (
        "You are running inside Skill Gate.\n"
        "Skills may be installed under `.skillgate/skills/`. "
        "Use one only if it fits the task. Do not assume a skill was pre-selected. "
        "If you use a skill, read its SKILL.md.\n"
        f"Task:\n{task}"
    )


def _claude_trigger_mode_prompt(task: str) -> str:
    """Trigger checks for Claude Code: native project skills only."""
    return (
        "You are running inside Skill Gate.\n"
        "Skills are installed under `.claude/skills/` in this workspace. "
        "Use Claude Code's Skill tool when one fits the task. "
        "Do not assume a skill was pre-selected.\n"
        f"Task:\n{task}"
    )


def _claude_discover_prompt(task: str, skills: list[Skill]) -> str:
    """No-trigger / unpinned for Claude Code."""
    catalog = "\n".join(f"- {s.name}: {s.description}" for s in skills)
    return (
        "You are running inside Skill Gate.\n"
        "No skill is pre-selected. Skills live under `.claude/skills/`. "
        "Read `.skillgate/catalog.md` if it exists for descriptions, "
        "then use the Skill tool to load at most one skill for the task. "
        "If none fits, complete the task without a skill and write "
        '{"skill": null} to `.skillgate/selected.json`.\n'
        "If you load a skill with the Skill tool, also write "
        '{"skill": "<name>"} to `.skillgate/selected.json`.\n\n'
        f"Skills:\n{catalog}\n\nTask:\n{task}"
    )


def _claude_skill_paths(skill_name: str) -> tuple[str, str]:
    skill_md = f".claude/skills/{skill_name}/SKILL.md"
    entry = f".claude/skills/{skill_name}/scripts/agent_entry.py"
    return skill_md, entry


def _claude_prompt(
    task: str,
    skills: list[Skill],
    *,
    pinned_skill: str | None = None,
) -> str:
    """Claude Code prompt when Gate pinned a skill (or explicit null pin)."""
    if pinned_skill:
        skill_md, entry = _claude_skill_paths(pinned_skill)
        parts = [
            "You are running inside Skill Gate.",
            f"The skill `{pinned_skill}` is already selected "
            "and written to `.skillgate/selected.json` for scorers. "
            "Do **not** read `.skillgate/catalog.md` or `.skillgate/selected.json`, "
            "open other skills, or rewrite the selection.",
            "Load and follow that skill using Claude Code's **Skill** tool "
            f"(project skills under `.claude/skills/`). You may read `{skill_md}` "
            "if you need the file on disk, but prefer the Skill tool when available.",
        ]
        if bins._pinned_has_agent_entry(skills, pinned_skill):
            parts.append(
                f"After loading the skill, before writing output files, run exactly:\n"
                f"  python3 {entry}\n"
                "Do **not** hand-write output files that script is meant to create."
            )
        else:
            parts.append(
                "After loading the skill, follow its SKILL.md and use bundled scripts "
                "when they exist."
            )
        parts.append("Put user-requested output files where the task says.")
        parts.append(f"Task:\n{task}")
        return "\n".join(parts)
    return (
        "You are running inside Skill Gate.\n"
        "No skill is selected for this check "
        '(.skillgate/selected.json has {"skill": null}). '
        "Do **not** use the Skill tool, browse `.skillgate/catalog.md`, "
        "or open anything under `.claude/skills/` or `.skillgate/skills/`. "
        "Complete the task without using skills.\n"
        f"Task:\n{task}"
    )


def claude_native_skills_enabled() -> bool:
    """Default on for Claude harness; opt out with SKILLGATE_CLAUDE_NATIVE_SKILLS=0."""
    raw = os.environ.get("SKILLGATE_CLAUDE_NATIVE_SKILLS", "").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def claude_config_isolation_enabled() -> bool:
    """Opt-in: isolated HOME/CLAUDE_CONFIG_DIR (breaks host CLI login unless you copy creds)."""
    raw = os.environ.get("SKILLGATE_CLAUDE_ISOLATE_CONFIG", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _agent_prompt(
    workspace: Path,
    task: str,
    skills: list[Skill],
    *,
    native_claude: bool = False,
) -> str:
    if _workspace_trigger_mode(workspace):
        if native_claude:
            return _claude_trigger_mode_prompt(task)
        return _trigger_mode_prompt(task)
    pinned = selection._read_selection(workspace)
    if pinned is _MISSING:
        if native_claude:
            return _claude_discover_prompt(task, skills)
        return _cursor_discover_prompt(task, skills)
    if native_claude:
        return _claude_prompt(task, skills, pinned_skill=pinned)
    return _cursor_prompt(task, skills, pinned_skill=pinned)


def _cursor_discover_prompt(task: str, skills: list[Skill]) -> str:
    """No-trigger / unpinned: the agent must choose from the catalog."""
    catalog = "\n".join(f"- {s.name}: {s.description}" for s in skills)
    return (
        "You are running inside Skill Gate.\n"
        "No skill is pre-selected. Read `.skillgate/catalog.md` if it exists, "
        "or use the skill names and descriptions below, and pick at most one "
        "skill for the user task. If none fits, complete the task without using "
        'a skill and write {"skill": null} to `.skillgate/selected.json`.\n'
        'If you pick a skill, write {"skill": "<name>"} to '
        "`.skillgate/selected.json`, then read that skill's SKILL.md and follow it.\n\n"
        f"Skills:\n{catalog}\n\nTask:\n{task}"
    )


def _cursor_prompt(
    task: str,
    skills: list[Skill],
    *,
    pinned_skill: str | None = None,
) -> str:
    """Build the agent prompt when Gate has already pinned a skill (or none).

    ``pinned_skill`` is the Gate skill (or ``None`` for an explicit null pin).
    Unpinned no-trigger checks use ``_cursor_discover_prompt`` instead.
    When pinned, the agent's first action must be a Read of that skill's SKILL.md.
    When that skill also ships ``scripts/agent_entry.py``, the second action must
    be a Shell that runs it — SKILL.md text alone is not enough to stop live
    agents from inventing output files (receipt-photo extract-image-stub RCA).
    """
    if pinned_skill:
        skill_md = f".skillgate/skills/{pinned_skill}/SKILL.md"
        entry = f".skillgate/skills/{pinned_skill}/scripts/agent_entry.py"
        parts = [
            "You are running inside Skill Gate.",
            f"The skill `{pinned_skill}` is already selected "
            "and written to `.skillgate/selected.json` for scorers. "
            "Do **not** read `.skillgate/catalog.md` or `.skillgate/selected.json`, "
            "open other skills, or rewrite the selection.",
            f"Your FIRST action must be a tool call that reads `{skill_md}` "
            "(Read / open that file). Do **not** emit assistant planning text, "
            "restate the task, or call any other tool before that Read.",
        ]
        if bins._pinned_has_agent_entry(skills, pinned_skill):
            parts.append(
                f"Your SECOND action — immediately after that Read, before any "
                f"Write / create / edit of output files — MUST be a Shell tool "
                f"call that runs exactly:\n"
                f"  python3 {entry}\n"
                "Do **not** hand-write, guess, OCR-invent, or otherwise author "
                "output files yourself. Only that script may create them. "
                "If it exits non-zero, fix the invocation and re-run it; never "
                "substitute your own JSON or text."
            )
        else:
            parts.append(
                "After reading SKILL.md, follow it to complete the task. "
                "Use bundled scripts under that skill when they exist."
            )
        parts.append("Put user-requested output files where the task says.")
        parts.append(f"Task:\n{task}")
        return "\n".join(parts)
    return (
        "You are running inside Skill Gate.\n"
        "No skill is selected for this check "
        '(.skillgate/selected.json has {"skill": null}). '
        "Do **not** browse `.skillgate/catalog.md`, open anything under "
        "`.skillgate/skills/`, or read any `SKILL.md`. "
        "Complete the task without using skills.\n"
        f"Task:\n{task}"
    )
