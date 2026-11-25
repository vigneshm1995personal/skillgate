"""Append-only pack-local eval history and deploy log."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from skillgate_ai.pack_io import (
    append_pack_line,
    glob_pack_files,
    is_pack_file,
    read_pack_text,
)
from skillgate_ai.paths import contained_path

HISTORY_DIR = "evals/history"
DEPLOY_REL = "evals/deploys.jsonl"


def _local_now() -> datetime:
    return datetime.now().astimezone()


def history_dir(pack_root: str | Path) -> Path:
    base = contained_path(pack_root)
    return contained_path(base, *HISTORY_DIR.split("/"))


def _read_jsonl_rel(pack_root: str | Path, rel: str) -> list[dict[str, Any]]:
    if not is_pack_file(pack_root, rel):
        return []
    try:
        text = read_pack_text(pack_root, rel)
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
    report: Mapping[str, Any] | None = None,
    error: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
    tryout: bool = False,
    gate_moved: bool | None = None,
) -> Path | None:
    """Append one JSONL row. Returns the file path, or None on EACCES/EROFS."""
    now = _local_now()
    rel = f"{HISTORY_DIR}/{now.strftime('%Y%m%d')}.jsonl"
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
        report_gate = str((report or {}).get("gate") or "")
        gate = "needs review" if report_gate == "needs review" else "green"
    elif passed is False:
        gate = "red"
    else:
        gate = None
    payload = json.dumps(
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
        ensure_ascii=True,
    )
    return append_pack_line(pack_root, rel, f"{payload}\n")


def _row_ts(item: Mapping[str, Any]) -> datetime:
    raw = item.get("ts")
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            pass
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed
    return datetime.min.replace(tzinfo=UTC)


def load_history(pack_root: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-last eval rows by ``ts``. Missing dir → empty list. Never reads the deploy log."""
    root = contained_path(pack_root)
    rows: list[dict[str, Any]] = []
    for path in glob_pack_files(root, HISTORY_DIR, "*.jsonl"):
        rel = f"{HISTORY_DIR}/{path.name}"
        for item in _read_jsonl_rel(root, rel):
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
    rel = f"{HISTORY_DIR}/{now.strftime('%Y%m%d')}.jsonl"
    payload = dict(row)
    payload.setdefault("ts", now.isoformat())
    payload.setdefault("kind", "compare")
    line = json.dumps(_scrub_compare_row(payload), ensure_ascii=True)
    return append_pack_line(pack_root, rel, f"{line}\n")


def load_compares(pack_root: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    """Newest-last compare rows. Does not include eval runs or deploy log."""
    root = contained_path(pack_root)
    rows: list[dict[str, Any]] = []
    for path in glob_pack_files(root, HISTORY_DIR, "*.jsonl"):
        rel = f"{HISTORY_DIR}/{path.name}"
        for item in _read_jsonl_rel(root, rel):
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
    payload = json.dumps(
        {
            "ts": _local_now().isoformat(),
            "kind": "deploy",
            "target": (target or "").strip().lower(),
            "status": status,
            "file_count": file_count,
            "mode": mode,
        },
        ensure_ascii=True,
    )
    return append_pack_line(pack_root, DEPLOY_REL, f"{payload}\n")


def load_deploys(pack_root: str | Path, *, limit: int = 50) -> list[dict[str, Any]]:
    rows = _read_jsonl_rel(pack_root, DEPLOY_REL)
    rows.sort(key=_row_ts)
    if limit > 0:
        return rows[-limit:]
    return rows
