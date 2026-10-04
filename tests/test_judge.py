from __future__ import annotations

from skillgate_ai.judge import SkipJudge


def test_skip_judge_does_not_pass_or_fail() -> None:
    judged = SkipJudge().judge("extract hello.pdf", [{"path": "out.txt", "present": True}], "selected: pdf")
    assert judged["status"] == "skip"
    assert judged["passed"] is None
    assert judged["cells"] == []
