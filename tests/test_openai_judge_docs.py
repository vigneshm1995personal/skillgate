from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs" / "judge.md"
PLAN = ROOT / "docs" / "plans" / "openai-judge.md"


def test_openai_judge_docs_are_plain() -> None:
    text = DOCS.read_text(encoding="utf-8")
    lower = text.lower()
    assert "pass/fail lock" not in lower
    assert "fallback if decisions is not enabled" not in lower
    assert "SKILLGATE_JUDGE_BACKEND=responses" in text
    assert "If your key can't use the newer scoring service" in text
    assert "does **not** compare the full output" in text or "does not compare the full output" in lower
    assert "expected and actual text" in lower or "full output" in lower
    assert "page counts" in lower or "contain this text" in lower
    assert "tasks[].judge.backend" not in text
    assert "task_completion.choice" not in text
    assert "built-in checker" not in lower
    assert "--harness demo" not in lower
    assert "fixture checks decide pass/fail" not in lower
    assert "otherwise fixture checks" not in lower
    assert "fixture checks decide the result" not in lower


def test_openai_judge_plan_drops_builtin_checker_and_demo_harness() -> None:
    text = PLAN.read_text(encoding="utf-8")
    lower = text.lower()
    assert "built-in checker" not in lower
    assert "this is not a live model" not in lower
    assert "--harness demo" not in lower
    assert "demo harness" not in lower
