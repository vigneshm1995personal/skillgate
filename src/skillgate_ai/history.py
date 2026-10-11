"""Append-only pack-local eval history under ``<pack>/evals/history/``."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_DIR = "evals/history"


def _local_now() -> datetime:
    return datetime.now().astimezone()


def history_dir(pack_root: str | Path) -> Path:
    return Path(pack_root).expanduser().resolve() / HISTORY_DIR


def latest_eval(pack_root: str | Path) -> dict[str, Any] | None:
    """Newest history row, or None when this pack has never been checked."""
    rows = load_history(pack_root, limit=1)
    return rows[-1] if rows else None


def append_eval(
    pack_root: str | Path,
    *,
    run_id: str,
    passed: bool,
    report: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> Path | None:
    """Append one JSONL row. Returns the file path, or None on EACCES/EROFS."""
    dest_dir = history_dir(pack_root)
    now = _local_now()
    stamp = now.strftime("%Y%m%d")
    dest = dest_dir / f"{stamp}.jsonl"
    row = {
        "ts": now.isoformat(),
        "run_id": run_id,
        "passed": passed,
        "gate": "green" if passed else "red",
        "report": report,
        "error": error,
        "config": config,
    }
    payload = json.dumps(row, ensure_ascii=True) + "\n"
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        with dest.open("a", encoding="utf-8") as handle:
            handle.write(payload)
    except OSError:
        return None
    return dest


def _row_ts(item: dict[str, Any]) -> datetime:
    raw = item.get("ts")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            pass
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
    return datetime.min.replace(tzinfo=timezone.utc)


def load_history(pack_root: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-last rows by ``ts``. Missing dir → empty list."""
    dest_dir = history_dir(pack_root)
    if not dest_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in dest_dir.glob("*.jsonl"):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                rows.append(item)
    rows.sort(key=_row_ts)
    if limit > 0:
        return rows[-limit:]
    return rows
