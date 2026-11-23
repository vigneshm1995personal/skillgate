"""Golden wire-shape tests (captured from main @ step 0)."""

from __future__ import annotations

import itertools
import json
import types

import pytest

import skillgate_ai.spans as spans_mod
from skillgate_ai.api_payloads import (
    AppState,
    history_payload,
    skill_version_rows,
    workspace_history,
)
from skillgate_ai.eval_config import EvalRunConfig, with_judge
from skillgate_ai.judge import SkipJudge, judge_stamp
from skillgate_ai.judge_context import (
    build_agent_trajectory,
    parse_command_runs,
    workspace_files_for_judge,
)
from skillgate_ai.metrics import evaluate_task_metrics, suite_metrics_summary
from skillgate_ai.scorers import Score
from skillgate_ai.spans import attr_map, spans_from_jsonl

STDOUT = """{"type":"tool_call","subtype":"started","tool_call":{"shellToolCall":{"args":{"command":"python make.py"}}}}
{"type":"tool_call","subtype":"started","tool_call":{"readToolCall":{"args":{"path":"skills/pdf/SKILL.md"}}}}
{"type":"item.completed","item":{"type":"file_change","changes":[{"path":"output/a.pdf"},{"path":"output/b.pdf"}]}}
{"type":"item.completed","item":{"type":"agent_message","text":"Done."}}
{"type":"assistant","timestamp_ms":1,"message":{"content":[{"type":"text","text":"Hel"}]}}
{"type":"assistant","timestamp_ms":2,"message":{"content":[{"type":"text","text":"lo"}]}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"t1","name":"Bash","input":{"command":"pytest -q"}}]}}
{"type":"error","message":"boom"}
{"type":"turn.failed","error":{"message":"bad turn"}}
not json"""

LOG = """{"type":"item.completed","item":{"type":"command_execution","command":"pytest -q","aggregated_output":"3 passed in 0.1s","exit_code":0}}
{"type":"tool_call","tool_call":{"shellToolCall":{"args":{"command":"ls"},"result":"a.txt"}}}
{"type":"assistant","message":{"content":[{"type":"tool_use","id":"c1","name":"Bash","input":{"command":"make test"}}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"c1","content":[{"type":"text","text":"ok"}]}]}}
{"type":"user","message":{"content":[{"type":"tool_result","tool_use_id":"zz","content":"orphan"}]}}
==== 2 passed in 0.2s ===="""

ARTIFACTS = [
    {"path": "output/a.txt", "present": True, "kind": "text", "body": "x" * 7000},
    {"path": "output/missing.txt", "present": False},
]

EXPECTED_SPANS = '[{"traceId": "trace", "spanId": "id00", "name": "eval.check", "kind": 1, "startTimeUnixNano": "1700000000000000000", "endTimeUnixNano": "1700000000009000000", "status": {"code": 1}, "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "invoke_agent"}}]}, {"traceId": "trace", "spanId": "id01", "name": "tool.shell", "kind": 1, "startTimeUnixNano": "1700000000001000000", "endTimeUnixNano": "1700000000001000000", "status": {"code": 1}, "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}}, {"key": "gen_ai.tool.name", "value": {"stringValue": "shell"}}, {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": "python make.py"}}], "parentSpanId": "id00"}, {"traceId": "trace", "spanId": "id02", "name": "tool.read", "kind": 1, "startTimeUnixNano": "1700000000002000000", "endTimeUnixNano": "1700000000002000000", "status": {"code": 1}, "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}}, {"key": "gen_ai.tool.name", "value": {"stringValue": "read"}}, {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": "skills/pdf/SKILL.md"}}, {"key": "file.path", "value": {"stringValue": "skills/pdf/SKILL.md"}}, {"key": "file.name", "value": {"stringValue": "SKILL.md"}}], "parentSpanId": "id00"}, {"traceId": "trace", "spanId": "id03", "name": "tool.write", "kind": 1, "startTimeUnixNano": "1700000000003000000", "endTimeUnixNano": "1700000000003000000", "status": {"code": 1}, "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}}, {"key": "gen_ai.tool.name", "value": {"stringValue": "write"}}, {"key": "file.path", "value": {"stringValue": "output/a.pdf"}}, {"key": "file.name", "value": {"stringValue": "a.pdf"}}, {"key": "file.paths", "value": {"stringValue": "output/a.pdf, output/b.pdf"}}], "parentSpanId": "id00"}, {"traceId": "trace", "spanId": "id04", "name": "gen_ai.assistant", "kind": 1, "startTimeUnixNano": "1700000000004000000", "endTimeUnixNano": "1700000000004000000", "status": {"code": 1}, "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}}, {"key": "gen_ai.assistant.message", "value": {"stringValue": "Done."}}], "parentSpanId": "id00"}, {"traceId": "trace", "spanId": "id05", "name": "gen_ai.assistant", "kind": 1, "startTimeUnixNano": "1700000000005000000", "endTimeUnixNano": "1700000000006000000", "status": {"code": 1}, "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "chat"}}, {"key": "gen_ai.assistant.message", "value": {"stringValue": "Hel lo"}}], "parentSpanId": "id00"}, {"traceId": "trace", "spanId": "id06", "name": "tool.shell", "kind": 1, "startTimeUnixNano": "1700000000007000000", "endTimeUnixNano": "1700000000007000000", "status": {"code": 1}, "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "execute_tool"}}, {"key": "gen_ai.tool.name", "value": {"stringValue": "bash"}}, {"key": "gen_ai.tool.call.arguments", "value": {"stringValue": "pytest -q"}}], "parentSpanId": "id00"}, {"traceId": "trace", "spanId": "id07", "name": "gen_ai.error", "kind": 1, "startTimeUnixNano": "1700000000008000000", "endTimeUnixNano": "1700000000008000000", "status": {"code": 2}, "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "error"}}, {"key": "error.message", "value": {"stringValue": "boom"}}], "parentSpanId": "id00"}, {"traceId": "trace", "spanId": "id08", "name": "gen_ai.error", "kind": 1, "startTimeUnixNano": "1700000000009000000", "endTimeUnixNano": "1700000000009000000", "status": {"code": 2}, "attributes": [{"key": "gen_ai.operation.name", "value": {"stringValue": "error"}}, {"key": "error.message", "value": {"stringValue": "bad turn"}}], "parentSpanId": "id00"}]'

EXPECTED_ATTR_MAP_1 = '{"gen_ai.operation.name": "execute_tool", "gen_ai.tool.name": "shell", "gen_ai.tool.call.arguments": "python make.py"}'

EXPECTED_CMD_RUNS = '[{"command": "pytest -q", "exit_code": 0, "output": "3 passed in 0.1s"}, {"command": "ls", "output": "a.txt"}, {"command": "make test", "output": "ok", "tool": "Bash"}, {"command": "", "output": "orphan"}, {"source": "transcript_line", "output": "==== 2 passed in 0.2s ===="}]'

EXPECTED_TRAJ = '{"had_path": true, "step_count": 3, "error_count": 0, "commands": [{"kind": "tool.shell", "tool": "shell", "args": "pytest -q", "file": null}, {"kind": "tool.shell", "tool": "shell", "args": "ls", "file": null}, {"kind": "tool.shell", "tool": "bash", "args": "make test", "file": null}], "command_runs": [{"command": "pytest -q", "exit_code": 0, "output": "3 passed in 0.1s"}, {"command": "ls", "output": "a.txt"}, {"command": "make test", "output": "ok", "tool": "Bash"}, {"command": "", "output": "orphan"}, {"source": "transcript_line", "output": "==== 2 passed in 0.2s ===="}], "test_mentions": ["{\\"type\\":\\"item.completed\\",\\"item\\":{\\"type\\":\\"command_execution\\",\\"command\\":\\"pytest -q\\",\\"aggregated_output\\":\\"3 passed in 0.1s\\",\\"exit_code\\":0}}", "==== 2 passed in 0.2s ====", "3 passed in 0.1s", "==== 2 passed in 0.2s ===="], "scorer_results": [{"scorer": "file_exists", "passed": true, "headline": "File exists", "detail": "ok"}, {"scorer": "rubric", "passed": false, "headline": null, "detail": "1/2"}], "transcript_chars": 601, "workspace_file_paths": ["output/a.txt"]}'

EXPECTED_WFFJ = '[{"path": "output/a.txt", "present": true, "kind": "text", "content": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"}, {"path": "output/missing.txt", "present": false, "kind": null, "content": null}]'

EXPECTED_M1 = '{"path": {"steps": 2, "errors": 0, "had_path": true}, "budgets": {"tokens_total": 10, "max_steps": 5}, "status": "fail", "reasons": ["This case went over its token budget."], "blocking": true}'

EXPECTED_M2 = '{"path": {"steps": 0, "errors": 0, "had_path": false}, "budgets": null, "status": "info", "reasons": [], "blocking": false}'

EXPECTED_SUITE = (
    '{"budget_fails": ["a"], "status": "fail", "path": {"steps": 2, "errors": 0, "had_path": true}}'
)

EXPECTED_JS_NONE = (
    '{"provider": "skip", "backend": "skip", "display_name": "Checks", "chosen": false}'
)

EXPECTED_JS_SKIP = (
    '{"provider": "skip", "backend": "skip", "display_name": "Checks", "chosen": false}'
)

EXPECTED_JS_NS = (
    '{"provider": "jev", "backend": "jev", "display_name": "Judge", "model": "m1", "chosen": true}'
)

EXPECTED_WITH_JUDGE = (
    '{"provider": "jev", "backend": "jev", "display_name": "Judge", "model": "m1", "chosen": true}'
)

EXPECTED_RELOADED_JUDGE = '{"provider": "jev", "backend": "jev", "display_name": "Judge", "model": "m1", "chosen": "True"}'

EXPECTED_HIST_PAYLOAD = '{"skill": "demo", "gate": "pending", "last_run": null, "last_deploy": {"id": 1, "target": "cursor", "status": "installed", "created_at": "2026-01-01T00:00:00Z", "file_count": 3, "mode": "local", "dest_label": "Editor agent\'s skills folder"}, "versions": [{"id": 1, "semver": "abc1234", "created_at": "2026-01-02T00:00:00Z", "skill_md_hash": "abc1234"}, {"id": 2, "semver": "def5678", "created_at": null, "skill_md_hash": "def5678"}], "runs": [], "deploys": [{"id": 1, "target": "cursor", "status": "installed", "created_at": "2026-01-01T00:00:00Z", "file_count": 3, "mode": "local", "dest_label": "Editor agent\'s skills folder"}], "timeline": [{"kind": "deploy", "id": 1, "at": "2026-01-01T00:00:00Z", "skill": "demo", "target": "cursor", "status": "installed", "label": "Install to Editor agent"}], "baseline": null}'

EXPECTED_WS_HIST = '{"skill": null, "gate": "pending", "last_run": null, "last_deploy": {"id": 1, "target": "cursor", "status": "installed", "created_at": "2026-01-01T00:00:00Z", "file_count": 3, "mode": "local", "dest_label": "Editor agent\'s skills folder"}, "versions": [], "runs": [], "deploys": [{"id": 1, "target": "cursor", "status": "installed", "created_at": "2026-01-01T00:00:00Z", "file_count": 3, "mode": "local", "dest_label": "Editor agent\'s skills folder"}], "timeline": [{"kind": "deploy", "id": 1, "at": "2026-01-01T00:00:00Z", "skill": "demo", "target": "cursor", "status": "installed", "label": "Install to Editor agent"}], "baseline": null}'

EXPECTED_VER_ROWS = '[{"id": 1, "semver": "abc1234", "created_at": "2026-01-02T00:00:00Z", "skill_md_hash": "abc1234"}, {"id": 2, "semver": "def5678", "created_at": null, "skill_md_hash": "def5678"}]'


@pytest.fixture
def span_patches(monkeypatch):
    counter = itertools.count()

    def fake_id(nbytes=8):
        return f"id{next(counter):02d}"

    monkeypatch.setattr(spans_mod, "_id", fake_id)
    monkeypatch.setattr(spans_mod, "_now_ns", lambda: 1_700_000_000_000_000_000)


def test_spans_from_jsonl_golden(monkeypatch, span_patches):
    result = spans_from_jsonl(STDOUT, trace_id="trace")
    assert json.dumps(result) == EXPECTED_SPANS
    assert json.dumps(attr_map(result[1])) == EXPECTED_ATTR_MAP_1


def test_parse_command_runs_golden():
    assert json.dumps(parse_command_runs(LOG)) == EXPECTED_CMD_RUNS


def test_build_agent_trajectory_golden(monkeypatch, span_patches):
    traj = build_agent_trajectory(
        spans=None,
        transcript=LOG,
        path={"steps": 3, "errors": 0, "had_path": True},
        scores=[
            Score(scorer="file_exists", passed=True, detail="ok", headline="File exists"),
            {"scorer": "rubric", "passed": False, "detail": "1/2"},
        ],
        artifacts=ARTIFACTS,
        command_log=None,
    )
    assert json.dumps(traj) == EXPECTED_TRAJ


def test_workspace_files_for_judge_golden():
    assert json.dumps(workspace_files_for_judge(ARTIFACTS)) == EXPECTED_WFFJ


def test_metrics_golden():
    m1 = evaluate_task_metrics(
        {"tokens_total": 50},
        None,
        "$ ls\nchanged a.txt\n",
        {"tokens_total": 10, "max_steps": 5},
    )
    m2 = evaluate_task_metrics(None, None, "", None)
    s = suite_metrics_summary([{"id": "a", "metrics": m1}, {"id": "b", "metrics": m2}])
    assert json.dumps(m1) == EXPECTED_M1
    assert json.dumps(m2) == EXPECTED_M2
    assert json.dumps(s) == EXPECTED_SUITE


def test_judge_stamp_golden():
    assert json.dumps(judge_stamp(None)) == EXPECTED_JS_NONE
    assert json.dumps(judge_stamp(SkipJudge())) == EXPECTED_JS_SKIP
    ns = types.SimpleNamespace(
        name="jev",
        backend=types.SimpleNamespace(name="jev", model="m1"),
        display_name="Judge",
        chosen=True,
    )
    assert json.dumps(judge_stamp(ns)) == EXPECTED_JS_NS
    stamp = judge_stamp(ns)
    cfg = with_judge(EvalRunConfig(), stamp)
    assert json.dumps(cfg.to_dict()["judge"]) == EXPECTED_WITH_JUDGE
    reloaded = EvalRunConfig.from_dict(with_judge(EvalRunConfig(), stamp).to_dict())
    assert json.dumps(reloaded.judge) == EXPECTED_RELOADED_JUDGE


def test_api_payloads_golden(tmp_path, monkeypatch):
    import skillgate_ai.api_payloads as api_payloads_mod

    skill_dir = tmp_path / "demo"
    skill_dir.mkdir()
    state = AppState(root=tmp_path)
    monkeypatch.setattr(api_payloads_mod, "load_history", lambda path, limit=50: [])
    monkeypatch.setattr(
        api_payloads_mod,
        "load_deploys",
        lambda path: [
            {
                "target": "cursor",
                "status": "installed",
                "ts": "2026-01-01T00:00:00Z",
                "file_count": 3,
                "mode": "local",
            }
        ],
    )
    monkeypatch.setattr(api_payloads_mod, "pack_gate_decision", lambda path: ("pending", None))
    monkeypatch.setattr(
        "skillgate_ai.compare_git.list_skill_git_versions",
        lambda path: [
            {"ref": "abc1234", "created_at": "2026-01-02T00:00:00Z"},
            {"ref": "def5678", "created_at": ""},
        ],
    )
    monkeypatch.setattr(
        api_payloads_mod,
        "catalog_entries",
        lambda root, **kw: [{"absolute": str(skill_dir)}],
    )
    assert json.dumps(history_payload(state, skill_dir)) == EXPECTED_HIST_PAYLOAD
    assert json.dumps(workspace_history(state)) == EXPECTED_WS_HIST
    assert json.dumps(skill_version_rows(skill_dir)) == EXPECTED_VER_ROWS
