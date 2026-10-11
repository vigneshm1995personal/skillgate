"""Local UI payloads. This server always applies the local gate (pass → cleared)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from skillgate_ai.case_pack import skill_has_dataset
from skillgate_ai.catalog import SOURCE_LABELS, catalog_entries
from skillgate_ai.eval_config import customer_config_label, harness_display_name
from skillgate_ai.history import load_deploys, load_history
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.pack import browser_files, relevant_eval_fixtures

SETTINGS_KEYS = (
    "CURSOR_API_KEY",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY",
)


@dataclass
class AppState:
    root: Path
    lock: threading.Lock = field(default_factory=threading.Lock)
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)


def state_of(request: Request) -> AppState:
    return request.app.state.ui


def fail(status: int, message: str, hint: str | None = None, **extra: Any) -> None:
    detail: dict[str, Any] = {"message": message}
    if hint:
        detail["hint"] = hint
    detail.update({key: value for key, value in extra.items() if value is not None})
    raise HTTPException(status_code=status, detail=detail)


def keys_payload(state: AppState) -> dict[str, Any]:
    from skillgate_ai.keys import key_presence

    return key_presence(state.root)


def is_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def local_gate(passed: bool | None, *, status: str, tryout: bool) -> tuple[str, str]:
    if tryout:
        return "pending", "Single-check runs do not unlock Install."
    if status == "error" or not passed:
        return "blocked", "Get a passing run to unlock Install."
    return "cleared", "Checks passed — Install is unlocked."


def _row_is_tryout(row: dict[str, Any], report: dict[str, Any] | None) -> bool:
    return bool(row.get("tryout") or (report or {}).get("tryout"))


def history_row_to_run(row: dict[str, Any], skill_path: Path) -> dict[str, Any]:
    report = row.get("report") if isinstance(row.get("report"), dict) else None
    passed = row.get("passed")
    error = row.get("error") if isinstance(row.get("error"), dict) else None
    harness = (report or {}).get("harness")
    tryout = _row_is_tryout(row, report)
    decision, reason = local_gate(passed, status="error" if error else "done", tryout=tryout)
    cfg = row.get("config") if isinstance(row.get("config"), dict) else None
    label = customer_config_label(cfg, str(harness or ""))
    return {
        "id": row.get("run_id"),
        "status": "error" if error else "done",
        "passed": passed,
        "gate": row.get("gate") or ("green" if passed else "red"),
        "gate_decision": decision,
        "gate_reason": reason,
        "error": error,
        "report": report,
        "created_at": row.get("ts"),
        "harness": harness,
        "config_label": label,
        "skill": (report or {}).get("skill") or skill_path.name,
        "skill_path": str(skill_path),
        "config": cfg,
        "completed_count": (report or {}).get("task_count"),
        "task_count": (report or {}).get("task_count"),
        "tryout": tryout,
    }


def _newest_full_run(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in runs:
        if not item.get("tryout"):
            return item
    return None


def _deploy_payload(row: dict[str, Any], *, index: int = 0) -> dict[str, Any]:
    target = str(row.get("target") or "")
    label = SOURCE_LABELS.get(target, target or "agent")
    dest_label = f"{label}'s skills folder"
    return {
        "id": index + 1,
        "target": target,
        "status": str(row.get("status") or "installed"),
        "created_at": row.get("ts"),
        "file_count": row.get("file_count"),
        "mode": row.get("mode") or "local",
        "dest_label": dest_label,
    }


def skill_payload(state: AppState, path: Path) -> dict[str, Any]:
    loaded = ingest_skill(path, strict=False)
    files = browser_files(path)
    hist = load_history(path, limit=50)
    runs = [history_row_to_run(row, path) for row in reversed(hist)]
    last_run = _newest_full_run(runs)
    last = hist[-1] if hist else None
    deploys = [_deploy_payload(row, index=i) for i, row in enumerate(load_deploys(path))]
    last_deploy = deploys[-1] if deploys else None
    gate = (last_run or {}).get("gate_decision") or "pending"
    slug = loaded.name or path.name
    display = loaded.display_name or path.name
    rel = path.name
    if is_relative(path, state.root):
        rel = str(path.relative_to(state.root))
    return {
        "id": slug,
        "name": display,
        "slug": slug,
        "description": loaded.description,
        "body": loaded.body,
        "warning": loaded.warning,
        "path": rel,
        "absolute": str(path.resolve()),
        "uploaded": False,
        "seed": slug == "pdf",
        "sabotaged": slug == "pdf-sabotaged",
        "gate": gate,
        "last_eval_at": last.get("ts") if last else None,
        "eval_count": len(hist),
        "deploy_count": len(deploys),
        "version_count": 0,
        "last_run": last_run,
        "last_deploy": last_deploy,
        "pack_files": files,
        "fixture_defaults": [
            {"src": item["src"], "dest": item["dest"], "bytes": item.get("bytes")}
            for item in relevant_eval_fixtures(path)
        ],
        "default_output_path": "output/result.txt",
        "has_dataset": skill_has_dataset(path),
    }


def history_payload(state: AppState, skill_path: Path) -> dict[str, Any]:
    del state
    rows = load_history(skill_path, limit=50)
    runs = [history_row_to_run(row, skill_path) for row in reversed(rows)]
    last_run = _newest_full_run(runs)
    gate = last_run.get("gate_decision") if last_run else "pending"
    deploys = [
        _deploy_payload(row, index=i) for i, row in enumerate(load_deploys(skill_path))
    ]
    last_deploy = deploys[-1] if deploys else None
    timeline = [
        {
            "kind": "run",
            "id": item.get("id"),
            "at": item.get("created_at"),
            "passed": item.get("passed"),
            "skill": item.get("skill"),
            "harness": item.get("harness"),
            "config_label": item.get("config_label"),
            "gate": item.get("gate"),
            "status": item.get("status"),
            "tryout": item.get("tryout"),
        }
        for item in runs
    ]
    for item in reversed(deploys):
        timeline.append(
            {
                "kind": "deploy",
                "id": item.get("id"),
                "at": item.get("created_at"),
                "skill": skill_path.name,
                "target": item.get("target"),
                "status": item.get("status"),
                "label": f"Install to {SOURCE_LABELS.get(item.get('target'), item.get('target') or 'agent')}",
            }
        )
    timeline.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
    return {
        "skill": skill_path.name,
        "gate": gate or "pending",
        "last_run": last_run,
        "last_deploy": last_deploy,
        "versions": [],
        "runs": runs,
        "deploys": list(reversed(deploys)),
        "timeline": timeline,
        "baseline": None,
    }


def workspace_history(state: AppState) -> dict[str, Any]:
    timeline: list[dict[str, Any]] = []
    deploys: list[dict[str, Any]] = []
    last_run = None
    last_deploy = None
    for entry in catalog_entries(state.root):
        hist = history_payload(state, Path(entry["absolute"]))
        timeline.extend(hist["timeline"])
        deploys.extend(hist.get("deploys") or [])
        if hist["last_run"] and (
            last_run is None
            or str(hist["last_run"].get("created_at") or "") > str(last_run.get("created_at") or "")
        ):
            last_run = hist["last_run"]
        if hist.get("last_deploy") and (
            last_deploy is None
            or str(hist["last_deploy"].get("created_at") or "")
            > str(last_deploy.get("created_at") or "")
        ):
            last_deploy = hist["last_deploy"]
    timeline.sort(key=lambda item: str(item.get("at") or ""), reverse=True)
    deploys.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    gate = last_run.get("gate_decision") if last_run else "pending"
    return {
        "skill": None,
        "gate": gate or "pending",
        "last_run": last_run,
        "last_deploy": last_deploy,
        "versions": [],
        "runs": [],
        "deploys": deploys[:50],
        "timeline": timeline[:50],
        "baseline": None,
    }


def run_from_history(state: AppState, run_id: str) -> dict[str, Any] | None:
    for entry in catalog_entries(state.root):
        path = Path(entry["absolute"])
        for row in load_history(path, limit=0):
            if str(row.get("run_id") or "") == run_id:
                return history_row_to_run(row, path)
    return None
