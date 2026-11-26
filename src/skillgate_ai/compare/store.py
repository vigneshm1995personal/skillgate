"""Compare runs: models (live arms) and versions (history / git)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from skillgate_ai.compare_control import (
    list_inflight_compares,
)
from skillgate_ai.history import load_compares
from skillgate_ai.paths import require_under


def find_compare(pack: Path, compare_id: str) -> dict[str, Any] | None:
    for row in load_compares(pack, limit=0):
        if row.get("compare_id") == compare_id:
            return row
    return None


def find_compare_anywhere(root: Path, compare_id: str) -> tuple[Path, dict[str, Any]] | None:
    from skillgate_ai.catalog import catalog_entries

    for entry in catalog_entries(root):
        path = require_under(root, entry["absolute"])
        row = find_compare(path, compare_id)
        if row:
            return path, row
    return None


def list_compares(pack: Path, *, limit: int = 20) -> list[dict[str, Any]]:
    return load_compares(pack, limit=limit)


def list_compares_merged(
    root: Path,
    pack: Path,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """In-flight compares first, then persisted rows (newest first), deduped by id."""
    from skillgate_ai.paths import require_under

    pack = require_under(root, pack)
    inflight = [
        {**row, "list_source": "inflight"}
        for row in list_inflight_compares(root)
        if str(row.get("skill") or "") == pack.name
    ]
    seen = {str(row.get("compare_id") or "") for row in inflight}
    on_disk = list(reversed(list_compares(pack, limit=limit)))
    return inflight + [
        {**row, "list_source": "disk"}
        for row in on_disk
        if str(row.get("compare_id") or "") not in seen
    ]


def strip_compare_list_meta(row: dict[str, Any]) -> dict[str, Any]:
    """Remove list-only fields before scrub/JSON output."""
    cleaned = dict(row)
    cleaned.pop("list_source", None)
    return cleaned
