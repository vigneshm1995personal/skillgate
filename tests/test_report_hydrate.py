from __future__ import annotations

from skillgate_ai.engine import EvalProgress, TaskProgress
from skillgate_ai.report.dicts import hydrate_report_spans, progress_to_dict


def test_progress_to_dict_running_task_keeps_transcript() -> None:
    task = TaskProgress(
        task_id="t1",
        prompt="p",
        status="running",
        transcript='{"type":"assistant","message":{"content":[]}}\n',
        spans=[],
    )
    progress = EvalProgress(
        suite="s",
        title="t",
        skill="pdf",
        harness="demo",
        task_count=1,
        completed_count=0,
        current_task_id="t1",
        tasks=[task],
    )
    payload = progress_to_dict(progress)
    assert payload["tasks"][0]["status"] == "running"
    assert "transcript" in payload["tasks"][0]


def test_hydrate_report_spans_rebuilds_from_transcript() -> None:
    payload = {
        "tasks": [
            {
                "id": "t1",
                "transcript": (
                    '{"type":"thread.started","thread_id":"1"}\n'
                    '{"type":"item.completed","item":{"type":"agent_message","text":"ok"}}\n'
                ),
            }
        ]
    }
    out = hydrate_report_spans(payload)
    spans = out["tasks"][0].get("spans")
    assert isinstance(spans, list)
    assert spans
