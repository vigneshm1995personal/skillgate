from __future__ import annotations

from pathlib import Path

from skillgate_ai.workspace_outputs import harness_final_answer, persist_harness_answer


def test_harness_final_answer_from_codex_agent_message() -> None:
    stdout = (
        '{"type":"item.completed","item":{"type":"agent_message","text":"Hello from Codex"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
    )
    assert harness_final_answer(stdout) == "Hello from Codex"


def test_persist_codex_answer_writes_answer_txt(tmp_path: Path) -> None:
    stdout = (
        '{"type":"item.completed","item":{"type":"agent_message","text":"saved answer"}}\n'
    )
    dest = persist_harness_answer(tmp_path, stdout)
    assert dest == tmp_path / "output" / "answer.txt"
    assert dest.read_text(encoding="utf-8") == "saved answer"


def test_harness_final_answer_from_cursor_result() -> None:
    stdout = '{"type":"result","result":"Hello from Cursor"}\n'
    assert harness_final_answer(stdout) == "Hello from Cursor"


def test_harness_final_answer_strips_cursor_narration() -> None:
    stdout = (
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"I\'ll read the skill first…"}]}}\n'
        '{"type":"tool_call","subtype":"started"}\n'
        '{"type":"assistant","message":{"content":[{"type":"text","text":'
        '"The PDF says hello."}]}}\n'
        '{"type":"result","result":"I\'ll read the skill first…\\nThe PDF says hello."}\n'
    )
    assert harness_final_answer(stdout) == "The PDF says hello."


def test_persist_cursor_answer_omits_narration(tmp_path: Path) -> None:
    stdout = (
        '{"type":"result","result":"I\'ll read the skill first…\\n\\nDone: 42"}\n'
    )
    dest = persist_harness_answer(tmp_path, stdout)
    assert dest is not None
    assert dest.read_text(encoding="utf-8") == "Done: 42"


def test_persist_does_not_overwrite_existing_output(tmp_path: Path) -> None:
    existing = tmp_path / "output" / "extracted.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("already here", encoding="utf-8")
    assert persist_harness_answer(tmp_path, '{"type":"item.completed","item":{"type":"agent_message","text":"nope"}}\n') is None
    assert existing.read_text(encoding="utf-8") == "already here"
