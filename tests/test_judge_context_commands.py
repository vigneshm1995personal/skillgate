from __future__ import annotations

import json
from pathlib import Path

from skillgate_ai.judge_context import (
    attach_adherence_context,
    attach_tool_check_evidence,
    build_agent_trajectory,
    parse_command_runs,
    skill_instructions_text,
    workspace_files_for_judge,
)


def test_parse_command_runs_codex_command_execution() -> None:
    line = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "pytest -q",
                "aggregated_output": "1 passed",
                "exit_code": 0,
            },
        }
    )
    runs = parse_command_runs(line)
    assert runs[0]["command"] == "pytest -q"
    assert "passed" in (runs[0].get("output") or "")


def test_parse_command_runs_claude_tool_use_and_result() -> None:
    use = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "tu1",
                        "name": "bash",
                        "input": {"command": "ls -la"},
                    }
                ]
            },
        }
    )
    result = json.dumps(
        {
            "type": "user",
            "message": {
                "content": [
                    {"type": "tool_result", "tool_use_id": "tu1", "content": "SKILL.md"},
                ]
            },
        }
    )
    runs = parse_command_runs(f"{use}\n{result}\n")
    assert runs
    assert runs[-1].get("output") == "SKILL.md"


def test_parse_command_runs_keeps_pytest_result_line() -> None:
    banner = "======================== 2 passed in 1.2s ========================\n"
    runs = parse_command_runs(banner)
    assert runs and "passed" in runs[0].get("output", "")


def test_skill_instructions_text_reads_skill_md(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    root.mkdir()
    (root / "SKILL.md").write_text(
        "---\nname: demo\ndescription: d\n---\n\n# Steps\nAlways test.\n",
        encoding="utf-8",
    )
    text = skill_instructions_text(root)
    assert text and "Always test" in text


def test_attach_adherence_context_enriches_question() -> None:
    questions = [
        {
            "name": "instruction_adherence",
            "instructions": "Followed the rules?",
            "choices": [{"value": "Fully followed", "description": ""}],
        }
    ]
    state = {
        "skill_instructions": "Rule 1: write tests.",
        "scorer_results": [{"scorer": "rubric", "passed": True, "detail": "ok"}],
        "artifacts": [{"path": "output/a.txt"}],
    }
    out = attach_adherence_context(questions, state)
    assert "Rules:" in out[0]["instructions"]
    assert "high confidence" in out[0]["choices"][0]["description"].lower()


def test_attach_tool_check_evidence_appends_predicate_block() -> None:
    questions = [
        {
            "type": "predicate",
            "name": "used_bash",
            "instructions": "Did the agent use bash?",
        }
    ]
    state = {
        "scorer_results": [
            {
                "scorer": "tool_calls",
                "passed": True,
                "detail": "bash ok",
                "headline": "Tool calls matched",
                "facts": {},
            }
        ]
    }
    out = attach_tool_check_evidence(questions, state)
    assert len(out[0]["instructions"]) > len(questions[0]["instructions"])


def test_build_agent_trajectory_prefers_command_log() -> None:
    command_log = json.dumps(
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "command": "make test",
                "aggregated_output": "ok",
            },
        }
    )
    traj = build_agent_trajectory(
        spans=[],
        transcript="",
        path=None,
        scores=[],
        command_log=command_log,
    )
    assert traj["command_runs"] and traj["command_runs"][0]["command"] == "make test"


def test_build_agent_trajectory_rebuilds_spans_from_transcript() -> None:
    transcript = '{"type":"function_call","name":"Read"}\n'
    traj = build_agent_trajectory(
        spans=[],
        transcript=transcript,
        path={"steps": 0, "errors": 0, "had_path": False},
        scores=[{"scorer": "rubric", "passed": True, "detail": "ok"}],
        artifacts=[{"path": "output/x.txt", "present": True}],
    )
    assert traj["transcript_chars"] == len(transcript)
    assert "output/x.txt" in traj["workspace_file_paths"]


def test_parse_command_runs_trims_non_shell_noise() -> None:
    from skillgate_ai.judge_context import _trim_command_runs

    filler = [{"command": "noop", "output": ""} for _ in range(40)]
    important = {"command": "pytest -q tests", "output": "1 passed", "tool": "shell"}
    runs = [*filler, important]
    trimmed = _trim_command_runs(runs)
    assert len(trimmed) <= 30
    assert any("pytest" in str(row.get("command")) for row in trimmed)


def test_workspace_files_for_judge_includes_present_rows() -> None:
    rows = workspace_files_for_judge(
        [
            {"path": "b.txt", "present": True, "body": "real", "kind": "text"},
        ]
    )
    assert rows[0]["content"] == "real"
