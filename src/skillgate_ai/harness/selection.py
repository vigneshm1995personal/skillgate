"""Skill selection parsing and writing under the sandbox workspace."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from skillgate_ai.errors import HarnessError
from skillgate_ai.ingest import Skill, canonical_skill_name

_SKILL_FILE_RE = re.compile(r"[^\s'\"`]+/(?:\.skillgate/|\.claude/)?skills/[^/\s'\"`]+/[^\s'\"`]+")


def _write_selection(workspace: Path, selected: str | None) -> None:
    target = workspace / ".skillgate" / "selected.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"skill": selected}), encoding="utf-8")


_MISSING = object()


def _read_selection(workspace: Path):
    """Pre-seeded skill name, ``None`` for null pin, or ``_MISSING`` if absent."""
    target = workspace / ".skillgate" / "selected.json"
    if not target.is_file():
        return _MISSING
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _MISSING
    if not isinstance(data, dict) or "skill" not in data:
        return _MISSING
    raw = data.get("skill")
    if raw is None:
        return None
    name = str(raw).strip()
    if name.lower() in {"", "none", "null"}:
        return None
    return name


def _parse_selected(workspace: Path, transcript: str, skills: list[Skill]) -> str | None:
    selected_path = workspace / ".skillgate" / "selected.json"
    if selected_path.is_file():
        try:
            data = json.loads(selected_path.read_text(encoding="utf-8"))
            return canonical_skill_name(data.get("skill"), skills)
        except json.JSONDecodeError:
            pass
    return _parse_skill_json(transcript, skills)


def _skill_tool_name_from_args(args: dict[str, Any]) -> str | None:
    for key in ("skill", "name", "skill_name", "skillName", "command"):
        raw = args.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _infer_from_skill_tool(blob: str, skills: list[Skill]) -> str | None:
    """Skill names from Claude/Cursor ``skillToolCall`` or ``tool_use`` Skill invocations."""
    known = {skill.name for skill in skills}
    found: list[str] = []
    for raw in blob.splitlines():
        line = raw.strip()
        if not line.startswith("{"):
            if "skillToolCall" in line or '"Skill"' in line:
                match = re.search(
                    r'"skill"\s*:\s*"([^"]+)"|"name"\s*:\s*"([^"]+)"',
                    line,
                )
                if match:
                    name = (match.group(1) or match.group(2) or "").strip()
                    resolved = canonical_skill_name(name, skills) or name
                    if resolved in known:
                        found.append(resolved)
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        if obj.get("type") == "tool_call" and obj.get("subtype") == "completed":
            continue
        chunks: list[dict[str, Any]] = []
        call = obj.get("tool_call")
        if isinstance(call, dict):
            for key, payload in call.items():
                if key.endswith("ToolCall") and isinstance(payload, dict):
                    tool = key[: -len("ToolCall")].lower()
                    args = payload.get("args")
                    chunks.append({"tool": tool, "args": args if isinstance(args, dict) else {}})
        message = obj.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "tool_use":
                    args = part.get("input")
                    chunks.append(
                        {
                            "tool": str(part.get("name") or "tool").strip().lower(),
                            "args": args if isinstance(args, dict) else {},
                        }
                    )
        if obj.get("type") == "tool_use":
            args = obj.get("input")
            chunks.append(
                {
                    "tool": str(obj.get("name") or "tool").strip().lower(),
                    "args": args if isinstance(args, dict) else {},
                }
            )
        for item in chunks:
            if item.get("tool") != "skill":
                continue
            raw_args = item.get("args")
            skill_args: dict[str, Any] = raw_args if isinstance(raw_args, dict) else {}
            name = _skill_tool_name_from_args(skill_args)
            if not name:
                continue
            resolved = canonical_skill_name(name, skills) or name
            if resolved in known:
                found.append(resolved)
    unique = list(dict.fromkeys(found))
    if len(unique) == 1:
        return unique[0]
    return None


def _skill_load_path(skill_name: str, workspace: Path) -> str:
    claude = workspace / ".claude" / "skills" / skill_name / "SKILL.md"
    if claude.is_file():
        return f".claude/skills/{skill_name}/SKILL.md"
    return f".skillgate/skills/{skill_name}/SKILL.md"


def _resolve_trigger_evidence(
    workspace: Path,
    transcript: str,
    skills: list[Skill],
    *,
    stdout: str = "",
    spans: list[dict] | None = None,
) -> tuple[str | None, list[str]]:
    """Selected skill + read paths for trigger scoring and the UI timeline."""
    selected = _parse_selected(workspace, transcript, skills)
    read_paths = _collect_read_paths(transcript, spans)
    skill_tool = _infer_from_skill_tool(f"{stdout}\n{transcript}", skills)
    if skill_tool is not None:
        selected = skill_tool
        marker = _skill_load_path(skill_tool, workspace)
        if marker not in read_paths:
            read_paths = [*read_paths, marker]
    elif selected is None:
        selected = _infer_from_reads(read_paths, skills)
    return selected, read_paths


def _parse_skill_json(text: str, skills: list[Skill]) -> str | None:
    match = re.search(r"\{[^{}]*\"skill\"[^{}]*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return canonical_skill_name(data.get("skill"), skills)


def _skill_for_selection(selected: str, skills: list[Skill]) -> Skill:
    name = canonical_skill_name(selected, skills) or selected
    for skill in skills:
        if skill.name == name:
            return skill
    raise HarnessError(
        f"Couldn't find skill {selected}.",
        hint="The folder name can be `pack` when the skill name differs.",
    )


def _parse_read_paths(transcript: str) -> list[str]:
    """Skill-folder paths from real tool/shell evidence only.

    Counts any file under ``skills/NAME/`` (not only ``SKILL.md``):

    - rendered Cursor/Codex lines (``$ read …``, ``$ cat …``)
    - raw stream-json / JSONL tool envelopes (``readToolCall``, ``"path":…``)
    - shell ``cat …/skills/NAME/…`` inside unrendered command strings

    Inject/prompt prose that merely mentions a skill path does **not**
    count — that avoids false ``no-trigger-unrelated`` fails when the null-pin
    preamble or assistant restates forbid-paths.
    """
    out: list[str] = []
    for line in transcript.splitlines():
        found = _SKILL_FILE_RE.findall(line.replace("\\", "/"))
        if not found:
            continue
        stripped = line.lstrip()
        if (
            stripped.startswith("$ ")
            or "readToolCall" in line
            or '"path"' in line
            or ("cat" in line and "/skills/" in line.replace("\\", "/"))
        ):
            out.extend(found)
    return out


def _parse_read_paths_from_spans(spans: list[dict] | None) -> list[str]:
    """Skill-folder paths recorded on tool spans (any file under skills/NAME/)."""
    from skillgate_ai.spans import attr_map

    out: list[str] = []
    for span in spans or []:
        if not isinstance(span, dict):
            continue
        attrs = attr_map(span)
        blob = " ".join(
            str(attrs.get(key) or "")
            for key in (
                "file.path",
                "gen_ai.tool.call.arguments",
                "gen_ai.tool.call.result",
            )
        )
        out.extend(_SKILL_FILE_RE.findall(blob.replace("\\", "/")))
    return out


def _collect_read_paths(transcript: str, spans: list[dict] | None = None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for path in _parse_read_paths(transcript) + _parse_read_paths_from_spans(spans):
        if path in seen:
            continue
        seen.add(path)
        found.append(path)
    return found


def _infer_from_reads(paths: list[str], skills: list[Skill]) -> str | None:
    names = set()
    for path in paths:
        named = _skill_name_from_path(path)
        if named and any(skill.name == named for skill in skills):
            names.add(named)
    if len(names) == 1:
        return next(iter(names))
    return None


def _skill_name_from_path(path: str) -> str | None:
    normalized = path.replace("\\", "/")
    match = re.search(r"(?:^|/)(?:\.skillgate/|\.claude/)?skills/([^/]+)/", normalized)
    if match:
        return match.group(1)
    return None
