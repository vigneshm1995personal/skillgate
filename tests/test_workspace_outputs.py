from __future__ import annotations

from pathlib import Path

from skillgate_ai.pack_files import GOLDEN_TAIL_CHARS, read_capped_text
from skillgate_ai.suite import FileExpect, ScorerSpec, TaskSpec
from skillgate_ai.workspace_outputs import (
    collect_workspace_outputs,
    expected_output_paths,
    harness_final_answer,
    iter_workspace_files,
    persist_harness_answer,
    snapshot_workspace,
)


def test_harness_final_answer_from_codex_agent_message() -> None:
    stdout = (
        '{"type":"item.completed","item":{"type":"agent_message","text":"Hello from Codex"}}\n'
        '{"type":"turn.completed","usage":{"input_tokens":1,"output_tokens":1}}\n'
    )
    assert harness_final_answer(stdout) == "Hello from Codex"


def test_persist_codex_answer_writes_answer_txt(tmp_path: Path) -> None:
    stdout = '{"type":"item.completed","item":{"type":"agent_message","text":"saved answer"}}\n'
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
    stdout = '{"type":"result","result":"I\'ll read the skill first…\\n\\nDone: 42"}\n'
    dest = persist_harness_answer(tmp_path, stdout)
    assert dest is not None
    assert dest.read_text(encoding="utf-8") == "Done: 42"


def test_persist_does_not_overwrite_existing_output(tmp_path: Path) -> None:
    existing = tmp_path / "output" / "extracted.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("already here", encoding="utf-8")
    assert (
        persist_harness_answer(
            tmp_path, '{"type":"item.completed","item":{"type":"agent_message","text":"nope"}}\n'
        )
        is None
    )
    assert existing.read_text(encoding="utf-8") == "already here"


def test_saved_artifact_body_is_not_capped_at_8kb(tmp_path: Path) -> None:
    html = "<html>" + ("x" * 12_000) + "</html>"
    dest = tmp_path / "output" / "report.html"
    dest.parent.mkdir(parents=True)
    dest.write_text(html, encoding="utf-8")
    rows = collect_workspace_outputs(
        TaskSpec(id="t1", prompt="write html", expect_skill="web", scorers=[]),
        tmp_path,
    )
    row = next(item for item in rows if item["path"] == "output/report.html")
    assert row["body"] == html
    assert len(row["body"]) > 8000


def test_judge_and_golden_reads_stay_capped(tmp_path: Path) -> None:
    blob = "y" * 12_000
    dest = tmp_path / "evals" / "goldens" / "big.txt"
    dest.parent.mkdir(parents=True)
    dest.write_text(blob, encoding="utf-8")
    capped = read_capped_text(dest)
    assert capped is not None
    assert len(capped) == GOLDEN_TAIL_CHARS
    from skillgate_ai.judge_context import workspace_files_for_judge

    rows = workspace_files_for_judge(
        [{"path": "output/a.html", "present": True, "body": "z" * 10_000}]
    )
    assert len(rows[0]["content"]) <= 6000


def test_expected_output_paths_collects_task_completion_files() -> None:
    task = TaskSpec(
        id="t1",
        prompt="write",
        expect_skill="pdf",
        scorers=[
            ScorerSpec(
                type="task_completion",
                files=[
                    FileExpect(path="output/a.txt"),
                    FileExpect(path="output/a.txt"),
                    FileExpect(path="output/b.txt"),
                ],
            )
        ],
    )
    assert expected_output_paths(task) == ["output/a.txt", "output/b.txt"]


def test_iter_workspace_files_skips_venv_dirnames(tmp_path: Path) -> None:
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "ok.txt").write_text("x", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "skip.txt").write_text("nope", encoding="utf-8")
    rels = {path.relative_to(tmp_path).as_posix() for path in iter_workspace_files(tmp_path)}
    assert "output/ok.txt" in rels
    assert not any(".venv" in rel for rel in rels)


def test_snapshot_workspace_records_sizes(tmp_path: Path) -> None:
    dest = tmp_path / "output" / "x.txt"
    dest.parent.mkdir(parents=True)
    dest.write_text("hello", encoding="utf-8")
    snap = snapshot_workspace(tmp_path)
    assert "output/x.txt" in snap
    size, _mtime = snap["output/x.txt"]
    assert size == 5


def test_collect_workspace_outputs_includes_git_artifacts(tmp_path: Path) -> None:
    import subprocess

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "output").mkdir()
    (tmp_path / "output" / "x.txt").write_text("hello", encoding="utf-8")
    subprocess.run(
        ["git", "add", "output/x.txt"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-c", "user.email=a@example.com", "-c", "user.name=Test", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    task = TaskSpec(id="t", prompt="p", expect_skill="demo", scorers=[])
    rows = collect_workspace_outputs(task, tmp_path)
    assert any(str(row.get("path", "")).startswith("git/") for row in rows)


def test_collect_workspace_outputs_with_baseline_ignores_unchanged(
    tmp_path: Path,
) -> None:
    skill = tmp_path / "skills" / "demo"
    skill.mkdir(parents=True)
    unchanged = tmp_path / "notes.txt"
    unchanged.write_text("same", encoding="utf-8")
    baseline = snapshot_workspace(tmp_path)
    task = TaskSpec(id="t", prompt="p", expect_skill="demo", scorers=[])
    rows = collect_workspace_outputs(task, tmp_path, baseline=baseline)
    paths = {row["path"] for row in rows}
    assert "notes.txt" not in paths


def test_output_row_omits_huge_non_output_file(tmp_path: Path) -> None:
    blob = tmp_path / "big.bin"
    blob.write_bytes(b"x" * 400_000)
    task = TaskSpec(id="t", prompt="p", expect_skill="demo", scorers=[])
    rows = collect_workspace_outputs(task, tmp_path)
    row = next(item for item in rows if item["path"] == "big.bin")
    assert row.get("omitted") == "size"


def test_harness_final_answer_prefers_codex_over_cursor_result() -> None:
    stdout = (
        '{"type":"item.completed","item":{"type":"agent_message","text":"Codex wins"}}\n'
        '{"type":"result","result":"Cursor loses"}\n'
    )
    assert harness_final_answer(stdout) == "Codex wins"
