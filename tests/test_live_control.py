from __future__ import annotations

from types import SimpleNamespace

import pytest

from skillgate_ai.live import (
    KILL,
    SKIP,
    CheckAborted,
    LiveLine,
    LiveTail,
    RunControl,
    StallDetector,
)


def test_live_tail_ring_buffer_and_serialization() -> None:
    tail = LiveTail(max_lines=2)
    tail.add("stdout", "one")
    tail.add("stderr", "two")
    tail.add("stdout", "three")
    assert tail.last_line == "three"
    assert len(tail) == 2
    assert tail.to_list() == [
        {"stream": "stderr", "text": "two"},
        {"stream": "stdout", "text": "three"},
    ]
    assert LiveLine("stdout", "x").to_dict() == {"stream": "stdout", "text": "x"}


def test_stall_detector_flags_repeating_lines() -> None:
    detector = StallDetector(silent_sec=100, repeat_count=3)
    detector.reset(now=0.0)
    detector.note("same", now=1.0)
    detector.note("same", now=2.0)
    detector.note("same", now=3.0)
    status = detector.status(now=3.0)
    assert status.stalled is True
    assert status.reason == "repeating"


def test_stall_detector_flags_silence() -> None:
    detector = StallDetector(silent_sec=5, repeat_count=3)
    detector.reset(now=0.0)
    status = detector.status(now=10.0)
    assert status.stalled is True
    assert status.reason == "silent"


def test_run_control_streams_rendered_lines() -> None:
    control = RunControl("run1")
    control.begin_task("t1", prompt="hello")
    control.on_line(
        "stdout",
        '{"type":"item.completed","item":{"type":"agent_message","text":"visible"}}',
    )
    snap = control.snapshot()
    assert any("visible" in line["text"] for line in snap["tail"])
    control.end_task()


def test_run_control_skip_and_kill_requests() -> None:
    control = RunControl("run1")
    control.begin_task("t1")
    assert control.request_skip() is True
    assert control.skip_requested is True
    assert control.should_abort() == SKIP
    assert control.request_kill() is True
    assert control.kill_requested is True
    assert control.should_abort() == KILL


def test_check_aborted_carries_reason() -> None:
    with pytest.raises(CheckAborted, match="skip"):
        raise CheckAborted("skip")


def test_run_control_registry_and_idle_snapshot() -> None:
    from skillgate_ai.live import create_control, drop_control, get_control, reset_controls

    reset_controls()
    control = create_control("run-a")
    assert get_control("run-a") is control
    assert control.snapshot()["task_id"] is None
    drop_control("run-a")
    assert get_control("run-a") is None


def test_run_control_flush_callbacks() -> None:
    seen: list[object] = []
    control = RunControl("run2")
    control.begin_task("t1")
    control.set_live_flush(lambda snap: seen.append(snap))
    control.set_poll_flush(lambda poll: seen.append(poll))
    control.persist_sandbox_poll({"status": "running"})
    control.notify_live()
    assert len(seen) == 2


def test_run_control_terminates_attached_process(monkeypatch: pytest.MonkeyPatch) -> None:
    terminated = []

    def fake_terminate(process: object, _signum: object) -> None:
        terminated.append(process)

    monkeypatch.setattr("skillgate_ai.live.signal_group", fake_terminate)
    process = SimpleNamespace(pid=123, poll=lambda: None, terminate=lambda: None)
    control = RunControl("run1")
    control.begin_task("t1")
    control.attach_process(process)
    control.request_kill()
    assert terminated == [process]
