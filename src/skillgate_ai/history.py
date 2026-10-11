"""Append-only pack-local eval history and deploy log."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_DIR = "evals/history"
DEPLOY_REL = "evals/deploys.jsonl"


def history_dir(pack_root: str | Path) -> Path:
    return Path(pack_root).expanduser().resolve() / HISTORY_DIR


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _append_jsonl(dest: Path, row: dict[str, Any]) -> Path | None:
    payload = json.dumps(row, ensure_ascii=True) + "\n"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("a", encoding="utf-8") as handle:
            handle.write(payload)
    except OSError:
        return None
    return dest


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
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
    return rows


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
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    dest = history_dir(pack_root) / f"{stamp}.jsonl"
    return _append_jsonl(
        dest,
        {
            "ts": _now(),
            "kind": "run",
            "run_id": run_id,
            "passed": passed,
            "gate": "green" if passed else "red",
            "report": report,
            "error": error,
            "config": config,
            "tryout": bool((report or {}).get("tryout")),
        },
    )


def load_history(pack_root: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-last eval rows. Missing dir → empty list. Never reads the deploy log."""
    dest_dir = history_dir(pack_root)
    if not dest_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(dest_dir.glob("*.jsonl")):
        for item in _read_jsonl(path):
            if item.get("kind") == "deploy" or not item.get("run_id"):
                continue
            rows.append(item)
    if limit > 0:
        return rows[-limit:]
    return rows


def append_deploy(
    pack_root: str | Path,
    *,
    target: str,
    status: str,
    file_count: int | None = None,
    mode: str = "local",
) -> Path | None:
    dest = Path(pack_root).expanduser().resolve() / DEPLOY_REL
    return _append_jsonl(
        dest,
        {
            "ts": _now(),
            "kind": "deploy",
            "target": (target or "").strip().lower(),
            "status": status,
            "file_count": file_count,
            "mode": mode,
        },
    )


def load_deploys(pack_root: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = _read_jsonl(Path(pack_root).expanduser().resolve() / DEPLOY_REL)
    if limit > 0:
        return rows[-limit:]
    return rows
