"""Local UI payloads. This server always applies the local gate (pass → cleared)."""

from __future__ import annotations

import copy
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request

from skillgate_ai.case_pack import skill_has_dataset
from skillgate_ai.catalog import SOURCE_LABELS, catalog_entries
from skillgate_ai.eval_config import customer_config_label
from skillgate_ai.history import load_deploys, load_history
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.judge_copy import customer_scorer_name
from skillgate_ai.deploy_gate import (
    local_gate,
    newest_gate_moving_row,
    pack_gate_decision,
    row_is_tryout,
    run_gate_decision,
)
from skillgate_ai.pack import browser_files, relevant_eval_fixtures

SETTINGS_KEYS = (
    "CURSOR_API_KEY",
    "CODEX_API_KEY",
    "OPENAI_API_KEY",
    "AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY",
    "JEV_API_KEY",
    "CLOUDFLARE_API_TOKEN",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
)


@dataclass
class AppState:
    root: Path
    lock: threading.Lock = field(default_factory=threading.Lock)
    runs: dict[str, dict[str, Any]] = field(default_factory=dict)
    compares: dict[str, dict[str, Any]] = field(default_factory=dict)

    def gate_busy(self) -> bool:
        with self.lock:
            if any(item.get("status") == "running" for item in self.runs.values()):
                return True
            return any(item.get("status") == "running" for item in self.compares.values())


def state_of(request: Request) -> AppState:
    return request.app.state.ui


def fail(status: int, message: str, hint: str | None = None, **extra: Any) -> None:
    detail: dict[str, Any] = {"message": message}
    if hint:
        detail["hint"] = hint
    detail.update({key: value for key, value in extra.items() if value is not None})
    raise HTTPException(status_code=status, detail=detail)


def keys_payload(state: AppState) -> dict[str, Any]:
    from skillgate_ai.keys import CUSTOMER_SETTINGS_KEYS, key_presence

    presence = key_presence(state.root)
    names = (*CUSTOMER_SETTINGS_KEYS, "JEV_API_KEY", "CLOUDFLARE_API_TOKEN")
    return {name: presence[name] for name in names}


def is_relative(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


_BROWSER_DROP = frozenset(
    {"config_label_raw", "check_kind", "provider", "backend", "via_gateway"}
)

# Live agent harnesses whose run model is a public id (not a provider secret).
LIVE_AGENT_HARNESSES = frozenset({"cursor-agent", "codex", "claude", "claude-code"})


def _scrub_judge(judge: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in judge.items():
        if key in _BROWSER_DROP or key == "model":
            continue
        out[key] = _scrub_browser(value)
    out["display_name"] = customer_scorer_name(judge)
    return out


def _scrub_config(item: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    keep_model = (str(item.get("harness") or "").strip().lower()) in LIVE_AGENT_HARNESSES
    for key, value in item.items():
        if key in _BROWSER_DROP:
            continue
        if key == "model":
            if keep_model:
                out[key] = _scrub_browser(value)
            continue
        if key == "judge" and isinstance(value, dict):
            out[key] = _scrub_judge(value)
            continue
        if key == "applied" and isinstance(value, dict):
            applied = {k: v for k, v in value.items() if k != "via_gateway"}
            if applied:
                out[key] = applied
            continue
        out[key] = _scrub_browser(value)
    out["label"] = customer_config_label(item)
    return out


def scrub_config(config: dict[str, Any] | None) -> dict[str, Any] | None:
    """Scrub a run config for on-disk history. Keeps the live agent model name."""
    if config is None:
        return None
    return _scrub_config(copy.deepcopy(config))


def _scrub_browser(value: Any) -> Any:
    if isinstance(value, list):
        return [_scrub_browser(item) for item in value]
    if not isinstance(value, dict):
        return value
    out: dict[str, Any] = {}
    for key, item in value.items():
        if key in _BROWSER_DROP:
            continue
        if key == "judge" and isinstance(item, dict):
            out[key] = _scrub_judge(item)
            continue
        if key == "config" and isinstance(item, dict):
            out[key] = _scrub_config(item)
            continue
        if key == "model" and isinstance(item, str):
            harness = str(value.get("harness") or "").strip().lower()
            if "arm_id" in value or harness in LIVE_AGENT_HARNESSES:
                out[key] = item
            continue
        out[key] = _scrub_browser(item)
    if "scored_by" in out and isinstance(out["scored_by"], str):
        stamp = out.get("judge") if isinstance(out.get("judge"), dict) else None
        if stamp is None and isinstance(out.get("config"), dict):
            inner = out["config"].get("judge")
            stamp = inner if isinstance(inner, dict) else None
        out["scored_by"] = _neutral_scored_by(out["scored_by"], stamp)
    return out


def _neutral_scored_by(text: str, stamp: dict[str, Any] | None) -> str:
    from skillgate_ai.judge_copy import SCORED_BY_JUDGE, scored_by_phrase

    lower = text.lower()
    leaky = "openai decisions" in lower or "vercel ai gateway" in lower or "openai couldn't" in lower
    if "couldn't" in lower or "could not" in lower:
        if not leaky:
            return text
        reason = text.split(". ", 1)[1].strip() if ". " in text else ""
        if reason and ("openai" in reason.lower() or "gateway" in reason.lower()):
            reason = ""
        base = "The judge couldn't score this run."
        return f"{base} {reason}".strip() if reason else base
    if "checks scored this run" in lower:
        return text
    if isinstance(stamp, dict) and stamp.get("display_name") and ("scored by" in lower or leaky):
        return scored_by_phrase(str(stamp.get("display_name")))
    if leaky:
        return SCORED_BY_JUDGE
    return text


def scrub_browser_payload(value: Any) -> Any:
    """Copy for the local UI. Provider/model names stay on disk unless the user picked."""
    return _scrub_browser(copy.deepcopy(value))


def history_row_to_run(row: dict[str, Any], skill_path: Path) -> dict[str, Any]:
    report = row.get("report") if isinstance(row.get("report"), dict) else None
    passed = row.get("passed")
    error = row.get("error") if isinstance(row.get("error"), dict) else None
    harness = (report or {}).get("harness")
    tryout = row_is_tryout(row, report)
    decision, reason = run_gate_decision(row)
    cfg = row.get("config") if isinstance(row.get("config"), dict) else None
    label = customer_config_label(cfg, str(harness or ""))
    return scrub_browser_payload(
        {
            "id": row.get("run_id"),
            "status": "error" if error else "done",
            "passed": passed,
            "gate": row.get("gate")
            if row.get("gate") is not None
            else (("green" if passed else "red") if passed is not None else None),
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
    )


def _gate_source_run(runs: list[dict[str, Any]], hist: list[dict[str, Any]]) -> dict[str, Any] | None:
    row = newest_gate_moving_row(hist)
    if row is None:
        return None
    run_id = str(row.get("run_id") or "")
    for item in runs:
        if str(item.get("id") or "") == run_id:
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
    last_run = _gate_source_run(runs, hist)
    last = hist[-1] if hist else None
    deploys = [_deploy_payload(row, index=i) for i, row in enumerate(load_deploys(path))]
    last_deploy = deploys[-1] if deploys else None
    gate, _gate_reason = pack_gate_decision(path)
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
        "version_count": len(skill_version_rows(path)),
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


def skill_version_rows(path: Path) -> list[dict[str, Any]]:
    """Versions Compare can use for this skill: one row per git ref."""
    from skillgate_ai.compare_git import list_skill_git_versions

    rows: list[dict[str, Any]] = []
    for index, item in enumerate(list_skill_git_versions(path)):
        rows.append(
            {
                "id": index + 1,
                "semver": item["ref"],
                "created_at": item["created_at"] or None,
                "skill_md_hash": item["ref"],
            }
        )
    return rows


def history_payload(state: AppState, skill_path: Path) -> dict[str, Any]:
    del state
    rows = load_history(skill_path, limit=50)
    runs = [history_row_to_run(row, skill_path) for row in reversed(rows)]
    last_run = _gate_source_run(runs, rows)
    gate, _gate_reason = pack_gate_decision(skill_path)
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
        "versions": skill_version_rows(skill_path),
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
