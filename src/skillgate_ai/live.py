"""Live run control: ring-buffered harness output, stall radar, skip/kill.

The worker thread streams harness stdout/stderr lines into a per-run
`RunControl` while it runs. `GET /api/runs/{id}` reads a snapshot on every
poll, so the Gate UI can show a live tail and a stall advisory without SSE.

Transports here are in-process only. The control is dropped when the run
reaches a terminal state.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Protocol

from skillgate_ai.spans import spans_from_jsonl
from skillgate_ai.usage import (
    Usage,
    is_non_content_stream_line,
    merge_usage,
    parse_usage_line,
    render_stream_line,
)

DEFAULT_TAIL_LINES = 60
DEFAULT_STALL_SILENT_SEC = 45.0
DEFAULT_STALL_REPEAT_COUNT = 5

SKIP = "skip"
KILL = "kill"


def _now() -> float:
    return time.monotonic()


class CheckAborted(Exception):
    """Raised inside a harness when the operator skips or kills the check."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"check aborted: {reason}")


class OutputSink(Protocol):
    """What the sandbox needs to stream a subprocess and be abortable."""

    def on_line(self, stream: str, text: str) -> None: ...

    def attach_process(self, process: Any) -> None: ...

    def detach_process(self) -> None: ...

    def should_abort(self) -> str | None: ...


@dataclass
class LiveLine:
    stream: str
    text: str

    def to_dict(self) -> dict[str, str]:
        return {"stream": self.stream, "text": self.text}


class LiveTail:
    """Bounded ring buffer of the last N harness output lines."""

    def __init__(self, max_lines: int = DEFAULT_TAIL_LINES) -> None:
        self.max_lines = max(1, max_lines)
        self._lines: deque[LiveLine] = deque(maxlen=self.max_lines)

    def add(self, stream: str, text: str) -> None:
        self._lines.append(LiveLine(stream=stream, text=text))

    def clear(self) -> None:
        self._lines.clear()

    @property
    def last_line(self) -> str | None:
        return self._lines[-1].text if self._lines else None

    def to_list(self) -> list[dict[str, str]]:
        return [line.to_dict() for line in self._lines]

    def __len__(self) -> int:
        return len(self._lines)


@dataclass
class StallStatus:
    stalled: bool = False
    reason: str | None = None
    silent_for_sec: float = 0.0
    repeat: int = 0
    last_line: str | None = None


class StallDetector:
    """Advisory only: silence past a threshold, or a repeating output line."""

    def __init__(
        self,
        *,
        silent_sec: float = DEFAULT_STALL_SILENT_SEC,
        repeat_count: int = DEFAULT_STALL_REPEAT_COUNT,
    ) -> None:
        self.silent_sec = silent_sec
        self.repeat_count = max(2, repeat_count)
        self._recent: deque[str] = deque(maxlen=self.repeat_count)
        self._started_at: float | None = None
        self._last_output_at: float | None = None
        self._last_line: str | None = None

    def reset(self, now: float | None = None) -> None:
        stamp = _now() if now is None else now
        self._recent.clear()
        self._started_at = stamp
        self._last_output_at = None
        self._last_line = None

    def note(self, text: str, now: float | None = None) -> None:
        stamp = _now() if now is None else now
        if self._started_at is None:
            self._started_at = stamp
        self._last_output_at = stamp
        self._last_line = text
        self._recent.append((text or "").strip())

    def status(self, now: float | None = None) -> StallStatus:
        stamp = _now() if now is None else now
        base = self._last_output_at if self._last_output_at is not None else self._started_at
        silent_for = max(0.0, stamp - base) if base is not None else 0.0
        repeat = self._repeat_run()
        if repeat >= self.repeat_count:
            return StallStatus(True, "repeating", silent_for, repeat, self._last_line)
        if base is not None and silent_for >= self.silent_sec:
            return StallStatus(True, "silent", silent_for, repeat, self._last_line)
        return StallStatus(False, None, silent_for, repeat, self._last_line)

    def _repeat_run(self) -> int:
        run = 0
        previous: str | None = None
        for line in reversed(self._recent):
            if not line:
                break
            if previous is None or line == previous:
                run += 1
                previous = line
            else:
                break
        return run


class RunControl:
    """Per-run live state. One active check at a time."""

    def __init__(
        self,
        run_id: str,
        *,
        max_lines: int = DEFAULT_TAIL_LINES,
        silent_sec: float = DEFAULT_STALL_SILENT_SEC,
        repeat_count: int = DEFAULT_STALL_REPEAT_COUNT,
    ) -> None:
        self.run_id = run_id
        self.tail = LiveTail(max_lines)
        self.stall = StallDetector(silent_sec=silent_sec, repeat_count=repeat_count)
        self._lock = threading.RLock()
        self._task_id: str | None = None
        self._prompt = ""
        self._started_at: float | None = None
        self._proc: Any | None = None
        self._skip_gen = 0
        self._skip_mark = 0
        self._kill = False
        self._output_count = 0
        self._usage = Usage()
        self._jsonl_buf: list[str] = []
        self._live_flush: Any | None = None
        self._poll_flush: Any | None = None

    # --- task lifecycle -------------------------------------------------
    def begin_task(self, task_id: str, prompt: str = "") -> RunControl:
        with self._lock:
            stamp = _now()
            self._task_id = task_id
            self._prompt = prompt or ""
            self._started_at = stamp
            self._proc = None
            self._skip_mark = self._skip_gen
            self._output_count = 0
            self._usage = Usage()
            self._jsonl_buf = []
            self.tail.clear()
            self.stall.reset(stamp)
        return self

    def end_task(self) -> None:
        with self._lock:
            self._task_id = None
            self._started_at = None
            self._proc = None

    # --- OutputSink -----------------------------------------------------
    def on_line(self, stream: str, text: str) -> None:
        with self._lock:
            if self._task_id is None:
                return
            update = parse_usage_line(text)
            if update is not None:
                self._usage = merge_usage(self._usage, update)
            self._output_count += 1
            if text.lstrip().startswith("{") and not is_non_content_stream_line(text):
                self._jsonl_buf.append(text)
            from skillgate_ai.harness import auth_failure_message

            stdout = "" if stream == "stderr" else text
            stderr = text if stream == "stderr" else ""
            if auth_failure_message(stdout, stderr):
                self._kill = True
                proc = self._proc
                if proc is not None:
                    self._terminate(proc)
            # Render Codex JSONL rows for the tail; usage-only rows are dropped.
            display = render_stream_line(text)
            if display is None:
                return
            self.tail.add(stream, display)
            self.stall.note(display)

    def note_usage(self, update: Usage) -> None:
        """Merge usage a harness reported off-stdout (e.g. an HTTP response).

        Streaming harnesses feed the sink line-by-line; non-streaming ones
        (BYOLLM HTTP) stamp the completed call here so the same snapshot and
        per-task usage apply to every harness.
        """
        with self._lock:
            if self._task_id is None:
                return
            self._usage = merge_usage(self._usage, update)

    def attach_process(self, process: Any) -> None:
        with self._lock:
            self._proc = process
            abort = self.should_abort()
        if abort:
            self._terminate(process)

    def detach_process(self) -> None:
        with self._lock:
            self._proc = None

    def should_abort(self) -> str | None:
        with self._lock:
            if self._kill:
                return KILL
            if self._skip_gen > self._skip_mark:
                return SKIP
            return None

    # --- operator actions ----------------------------------------------
    def request_skip(self) -> bool:
        """Idempotent. True when this call newly requested a skip."""
        with self._lock:
            if self._kill:
                return False
            newly = self._skip_gen == self._skip_mark
            self._skip_gen += 1
            proc = self._proc
        if proc is not None:
            self._terminate(proc)
        return newly

    def request_kill(self) -> bool:
        """Idempotent. True when this call newly requested a kill."""
        with self._lock:
            newly = not self._kill
            self._kill = True
            proc = self._proc
        if proc is not None:
            self._terminate(proc)
        return newly

    @property
    def skip_requested(self) -> bool:
        with self._lock:
            return self._skip_gen > self._skip_mark

    @property
    def kill_requested(self) -> bool:
        with self._lock:
            return self._kill

    # --- live durable flush (hosted Sandbox mid-check) --------------------
    def set_live_flush(self, fn: Any | None) -> None:
        """Register a callback invoked by ``notify_live`` with ``snapshot()``."""
        with self._lock:
            self._live_flush = fn

    def set_poll_flush(self, fn: Any | None) -> None:
        """Register a callback that persists ``sandbox_poll`` mid-launch / mid-poll."""
        with self._lock:
            self._poll_flush = fn

    def persist_sandbox_poll(self, poll: dict[str, Any]) -> None:
        """Flush durable sandbox job state when a callback is registered."""
        with self._lock:
            flush = self._poll_flush
        if flush is None:
            return
        try:
            flush(poll)
        except Exception:  # noqa: BLE001 - never break the harness on flush
            pass

    def notify_live(self) -> None:
        """Push current spans/transcript to durable progress if a callback is set."""
        with self._lock:
            flush = self._live_flush
            if flush is None or self._task_id is None:
                return
        try:
            flush(self.snapshot())
        except Exception:  # noqa: BLE001 - never break the harness on flush
            pass

    # --- read model -----------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = _now()
            if self._task_id is None:
                stall = StallStatus()
                elapsed: float | None = None
                last_line = None
            else:
                stall = self.stall.status(now)
                start = self._started_at
                elapsed = None if start is None else max(0.0, now - start)
                last_line = stall.last_line
            return {
                "task_id": self._task_id,
                "prompt": self._prompt,
                "tail": self.tail.to_list(),
                "spans": spans_from_jsonl("\n".join(self._jsonl_buf)) if self._jsonl_buf else [],
                "transcript": "\n".join(self._jsonl_buf) if self._jsonl_buf else "",
                "elapsed_sec": None if elapsed is None else round(elapsed, 3),
                "stalled": stall.stalled,
                "stall_reason": stall.reason,
                "silent_for_sec": round(stall.silent_for_sec, 3),
                "repeat_count": stall.repeat,
                "last_line": last_line,
                "output_count": self._output_count,
                "skip_requested": self._skip_gen > self._skip_mark,
                "kill_requested": self._kill,
                **self._usage.to_dict(),
            }

    def usage_dict(self) -> dict[str, Any] | None:
        """Per-task usage for the report, or None when the harness reported none."""
        with self._lock:
            return self._usage.to_dict() if self._usage.known else None

    def _terminate(self, process: Any) -> None:
        try:
            process.terminate()
        except Exception:  # noqa: BLE001 - best effort
            return
        poll = getattr(process, "poll", None)
        if not callable(poll):
            return

        def hard_kill() -> None:
            try:
                if process.poll() is None:
                    process.kill()
            except Exception:  # noqa: BLE001, S110 - best effort
                pass

        timer = threading.Timer(2.0, hard_kill)
        timer.daemon = True
        timer.start()


_CONTROLS: dict[str, RunControl] = {}
_CONTROLS_LOCK = threading.Lock()


def create_control(run_id: str, **kwargs: Any) -> RunControl:
    control = RunControl(run_id, **kwargs)
    with _CONTROLS_LOCK:
        _CONTROLS[run_id] = control
    return control


def get_control(run_id: str) -> RunControl | None:
    with _CONTROLS_LOCK:
        return _CONTROLS.get(run_id)


def drop_control(run_id: str) -> None:
    with _CONTROLS_LOCK:
        _CONTROLS.pop(run_id, None)


def reset_controls() -> None:
    with _CONTROLS_LOCK:
        _CONTROLS.clear()
