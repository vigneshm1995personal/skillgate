"""Judge-facing context: extracted file text, agent trajectory, skill instructions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from skillgate_ai.document_text import extract_document_text
from skillgate_ai.pack_files import GOLDEN_TAIL_CHARS, read_capped_text
from skillgate_ai.scorers import Score
from skillgate_ai.spans import attr_map

_TEST_LINE_RE = re.compile(
    r"\b(pytest|vitest|pnpm test|npm test|cargo test|go test|unittest)\b",
    re.IGNORECASE,
)


def enrich_output_row(row: dict[str, Any], dest: Path) -> dict[str, Any]:
    """Attach extracted text for binary office/PDF outputs."""
    if not row.get("present"):
        return row
    extracted = extract_document_text(dest)
    if not extracted:
        return row
    row["extracted_text"] = extracted
    if row.get("body") is None or row.get("kind") == "bytes":
        row["body"] = extracted
    return row


def skill_instructions_text(skill_root: Path | None, *, fallback: str | None = None) -> str | None:
    if fallback and str(fallback).strip():
        return _cap_instructions(fallback)
    if skill_root is None:
        return None
    skill_md = skill_root / "SKILL.md"
    if not skill_md.is_file():
        return None
    return _cap_instructions(read_capped_text(skill_md) or "")


def build_agent_trajectory(
    *,
    spans: list[dict[str, Any]] | None,
    transcript: str,
    path: dict[str, Any] | None,
    scores: list[Score] | list[dict[str, Any]] | None,
) -> dict[str, Any]:
    commands: list[dict[str, Any]] = []
    for span in spans or []:
        name = str(span.get("name") or "")
        if not (name.startswith("tool.") or name == "skill.select"):
            continue
        attrs = attr_map(span)
        commands.append(
            {
                "kind": name,
                "tool": attrs.get("gen_ai.tool.name"),
                "args": str(attrs.get("gen_ai.tool.call.arguments") or "")[:500],
                "file": attrs.get("file.path"),
            }
        )
    test_mentions: list[str] = []
    for line in (transcript or "").splitlines():
        if _TEST_LINE_RE.search(line):
            test_mentions.append(line.strip()[:500])
    scorer_rows: list[dict[str, Any]] = []
    for item in scores or []:
        if isinstance(item, Score):
            scorer_rows.append(
                {
                    "scorer": item.scorer,
                    "passed": item.passed,
                    "headline": item.headline,
                    "detail": item.detail,
                }
            )
        elif isinstance(item, dict):
            scorer_rows.append(
                {
                    "scorer": item.get("scorer"),
                    "passed": item.get("passed"),
                    "headline": item.get("headline"),
                    "detail": item.get("detail"),
                }
            )
    path_info = path if isinstance(path, dict) else {}
    return {
        "had_path": path_info.get("had_path"),
        "step_count": path_info.get("steps"),
        "error_count": path_info.get("errors"),
        "commands": commands[:40],
        "test_mentions": test_mentions[:20],
        "scorer_results": scorer_rows,
        "transcript_chars": len(transcript or ""),
    }


def _cap_instructions(text: str) -> str | None:
    cleaned = str(text or "").strip()
    if not cleaned:
        return None
    if len(cleaned) <= GOLDEN_TAIL_CHARS:
        return cleaned
    return cleaned[:GOLDEN_TAIL_CHARS]
