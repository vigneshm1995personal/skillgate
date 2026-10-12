"""Append-only pack-local eval history and deploy log."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HISTORY_DIR = "evals/history"
DEPLOY_REL = "evals/deploys.jsonl"


def _local_now() -> datetime:
    return datetime.now().astimezone()


def history_dir(pack_root: str | Path) -> Path:
    return Path(pack_root).expanduser().resolve() / HISTORY_DIR


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


def latest_eval(pack_root: str | Path) -> dict[str, Any] | None:
    """Newest history row, or None when this pack has never been checked."""
    rows = load_history(pack_root, limit=1)
    return rows[-1] if rows else None


def append_eval(
    pack_root: str | Path,
    *,
    run_id: str,
    passed: bool | None,
    report: dict[str, Any] | None = None,
    error: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    tryout: bool = False,
    gate_moved: bool | None = None,
) -> Path | None:
    """Append one JSONL row. Returns the file path, or None on EACCES/EROFS."""
    now = _local_now()
    dest = history_dir(pack_root) / f"{now.strftime('%Y%m%d')}.jsonl"
    from skillgate_ai.deploy_gate import infer_gate_moved

    is_tryout = tryout or bool((report or {}).get("tryout"))
    moved = infer_gate_moved(
        tryout=is_tryout,
        error=error if isinstance(error, dict) else None,
        passed=passed,
        explicit=gate_moved,
    )
    gate: str | None
    if not moved:
        gate = None
    elif passed is True:
        gate = "green"
    elif passed is False:
        gate = "red"
    else:
        gate = None
    return _append_jsonl(
        dest,
        {
            "ts": now.isoformat(),
            "kind": "run",
            "run_id": run_id,
            "passed": passed,
            "gate": gate,
            "report": report,
            "error": error,
            "config": config,
            "tryout": is_tryout,
            "gate_moved": moved,
        },
    )


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
    """Newest-last eval rows by ``ts``. Missing dir → empty list. Never reads the deploy log."""
    dest_dir = history_dir(pack_root)
    if not dest_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in dest_dir.glob("*.jsonl"):
        for item in _read_jsonl(path):
            if item.get("kind") in {"deploy", "compare"}:
                continue
            if not item.get("run_id"):
                continue
            rows.append(_scrub_history_row(item))
    rows.sort(key=_row_ts)
    if limit > 0:
        return rows[-limit:]
    return rows


def _scrub_compare_row(row: dict[str, Any]) -> dict[str, Any]:
    from skillgate_ai.compare import scrub_customer_compare_payload

    cleaned = scrub_customer_compare_payload(row)
    if row.get("ts"):
        cleaned["ts"] = row["ts"]
    cleaned.setdefault("kind", "compare")
    return cleaned


def append_compare(pack_root: str | Path, *, row: dict[str, Any]) -> Path | None:
    """Append one compare job row to pack history JSONL."""
    now = _local_now()
    dest = history_dir(pack_root) / f"{now.strftime('%Y%m%d')}.jsonl"
    payload = dict(row)
    payload.setdefault("ts", now.isoformat())
    payload.setdefault("kind", "compare")
    return _append_jsonl(dest, _scrub_compare_row(payload))


def load_compares(pack_root: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-last compare rows. Does not include eval runs or deploy log."""
    dest_dir = history_dir(pack_root)
    if not dest_dir.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in dest_dir.glob("*.jsonl"):
        for item in _read_jsonl(path):
            if item.get("kind") != "compare" or not item.get("compare_id"):
                continue
            rows.append(_scrub_compare_row(item))
    rows.sort(key=_row_ts)
    if limit > 0:
        return rows[-limit:]
    return rows


def _scrub_history_row(row: dict[str, Any]) -> dict[str, Any]:
    from skillgate_ai.api_payloads import scrub_browser_payload

    return scrub_browser_payload(row)


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
            "ts": _local_now().isoformat(),
            "kind": "deploy",
            "target": (target or "").strip().lower(),
            "status": status,
            "file_count": file_count,
            "mode": mode,
        },
    )


def load_deploys(pack_root: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = _read_jsonl(Path(pack_root).expanduser().resolve() / DEPLOY_REL)
    rows.sort(key=_row_ts)
    if limit > 0:
        return rows[-limit:]
    return rows
