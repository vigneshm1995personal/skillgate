"""Headless run table: start a check on a worker thread, poll it, skip/kill it.

Shared by the local UI (api_runs) and the MCP server. No FastAPI.
"""

from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from skillgate_ai.deploy_gate import local_gate
from skillgate_ai.errors import SkillGateError, timeout_harness_error
from skillgate_ai.gate import run_check
from skillgate_ai.live import create_control, drop_control, get_control
from skillgate_ai.report import progress_to_dict, report_to_dict

RunRecord = dict[str, Any]

HARNESS_PREFS = frozenset({"auto", "cursor-agent", "codex", "claude"})
BUSY_MESSAGE = "A check or compare is already running."


class RunBusyError(SkillGateError):
    """Another check/compare is running in this process. Cannot run, not a fail."""

    exit_code = 2


@dataclass(frozen=True)
class RunRequest:
    skill_path: Path
    harness: str = "auto"
    checks: list[dict[str, Any]] | None = None
    config: dict[str, Any] = field(default_factory=dict)
    tryout: bool = False
    no_judge: bool = False
    source: str = "ui"


def attach_stamped_config(record: RunRecord, report: dict[str, Any] | None) -> None:
    """Replace the request config with the resolved stamp so UI Result/Metrics match the run."""
    from skillgate_ai.eval_config import EvalRunConfig, customer_run_details

    stamped = report.get("config") if isinstance(report, dict) else None
    if isinstance(stamped, dict):
        merged = dict(stamped)
        cfg = EvalRunConfig.from_dict(merged)
        if cfg is not None:
            merged["label"] = customer_run_details(cfg)
        record["config"] = merged


def resolve_harness(config: dict[str, Any], requested: str | None) -> str:
    """config.harness_pref wins if it's a known pref, else requested, else 'auto'."""
    pref = str(config.get("harness_pref") or "").strip().lower()
    req = str(requested or "").strip().lower()
    if pref in HARNESS_PREFS:
        return pref
    return req or "auto"


class RunRegistry:
    def __init__(
        self,
        root: Path,
        *,
        runs: dict[str, RunRecord] | None = None,
        lock: threading.Lock | None = None,
        busy: Callable[[], bool] | None = None,
    ) -> None:
        self.root = root
        self.runs = runs if runs is not None else {}
        self.lock = lock if lock is not None else threading.Lock()
        self._busy_pred = busy
        self._threads: dict[str, threading.Thread] = {}

    def busy(self) -> bool:
        if self._busy_pred is not None:
            return self._busy_pred()
        with self.lock:
            return any(record.get("status") == "running" for record in self.runs.values())

    def start(self, request: RunRequest) -> dict[str, str]:
        if self.busy():
            raise RunBusyError(BUSY_MESSAGE)
        run_id = uuid.uuid4().hex[:12]
        checks = request.checks
        config = request.config
        tryout = request.tryout
        seed: RunRecord = {
            "id": run_id,
            "status": "running",
            "passed": None,
            "gate": None,
            "gate_decision": "pending",
            "skill": request.skill_path.name,
            "skill_path": str(request.skill_path),
            "harness": request.harness,
            "tryout": tryout,
            "completed_count": 0,
            "task_count": len(checks) if checks else None,
            "current_task_id": None,
            "error": None,
            "report": None,
            "config": config,
            "model": config.get("model"),
            "timeout_sec": config.get("timeout_sec"),
            "temperature": config.get("temperature"),
            "reasoning_effort": config.get("reasoning_effort"),
        }
        with self.lock:
            self.runs[run_id] = seed
        create_control(run_id)
        thread = threading.Thread(
            target=self._work,
            args=(run_id, request),
            name=f"skillgate-run-{run_id}",
            daemon=True,
        )
        self._threads[run_id] = thread
        thread.start()
        return {"id": run_id, "status": "running"}

    def get(self, run_id: str) -> RunRecord | None:
        with self.lock:
            record = self.runs.get(run_id)
            if record is None:
                return None
            return copy.deepcopy(record)

    def skip(self, run_id: str) -> bool:
        control = get_control(run_id)
        if control is None:
            return False
        control.request_skip()
        return True

    def kill(self, run_id: str) -> bool:
        control = get_control(run_id)
        if control is None:
            return False
        control.request_kill()
        return True

    def join(self, run_id: str, timeout: float | None = None) -> bool:
        thread = self._threads.get(run_id)
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _work(self, run_id: str, request: RunRequest) -> None:
        record = self.runs[run_id]
        control = get_control(run_id)
        config = request.config
        tryout = request.tryout
        checks = request.checks
        try:

            def on_progress(progress) -> None:
                payload = progress_to_dict(progress)
                record["report"] = payload
                record["completed_count"] = payload.get("completed_count")
                record["task_count"] = payload.get("task_count")
                record["current_task_id"] = payload.get("current_task_id")
                record["harness"] = payload.get("harness") or record.get("harness")

            harness = resolve_harness(config, request.harness)
            result = run_check(
                request.skill_path,
                harness=harness,
                on_progress=on_progress,
                control=control,
                run_id=run_id,
                source=request.source,
                root=self.root,
                checks=[dict(item) for item in checks] if checks else None,
                model=config.get("model"),
                timeout=config.get("timeout_sec"),
                temperature=config.get("temperature"),
                reasoning_effort=config.get("reasoning_effort"),
                tryout=tryout,
                no_judge=request.no_judge,
            )
            report = report_to_dict(result.report) if result.report is not None else None
            if report is not None and tryout:
                report["tryout"] = True
            status = "error" if result.error else "done"
            passed = None if result.report is None else result.report.passed
            final_harness = (report or {}).get("harness") or record.get("harness")
            decision, reason = local_gate(passed, status=status, tryout=tryout, report=report)
            record.update(
                {
                    "status": status,
                    "passed": passed,
                    "gate": (report or {}).get("gate"),
                    "gate_decision": decision,
                    "gate_reason": reason,
                    "error": result.error,
                    "report": report,
                    "harness": final_harness,
                    "demo_notice": result.demo_notice,
                    "tryout": tryout,
                    "exit_code": result.exit_code,
                    "completed_count": (report or {}).get("task_count"),
                    "task_count": (report or {}).get("task_count"),
                }
            )
            attach_stamped_config(record, report)
        except Exception as exc:  # noqa: BLE001 — surface to the poller
            exit_code: int | None
            blocked = timeout_harness_error(exc)
            if blocked is not None:
                message = blocked.message
                hint = blocked.hint
                exit_code = blocked.exit_code
            else:
                message = exc.message if isinstance(exc, SkillGateError) else str(exc)
                hint = getattr(exc, "hint", None)
                exit_code = getattr(exc, "exit_code", None)
            decision, reason = local_gate(None, status="error", tryout=tryout, gate_moved=False)
            record.update(
                {
                    "status": "error",
                    "passed": None,
                    "gate": None,
                    "gate_decision": decision,
                    "gate_reason": reason,
                    "error": {"message": message, "hint": hint},
                    "tryout": tryout,
                    "exit_code": exit_code,
                }
            )
        finally:
            drop_control(run_id)
