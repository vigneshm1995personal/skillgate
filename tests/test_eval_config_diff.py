from __future__ import annotations

from skillgate_ai.eval_config import EvalRunConfig, diff_eval_config


def test_diff_eval_config_reports_model_change() -> None:
    previous = EvalRunConfig(harness="codex", model="a", timeout_sec=60, temperature=0)
    current = EvalRunConfig(harness="codex", model="b", timeout_sec=60, temperature=0)
    entries = diff_eval_config(current, previous)
    fields = {row["field"] for row in entries}
    assert "model" in fields


def test_diff_eval_config_empty_when_fingerprints_missing() -> None:
    assert diff_eval_config(None, EvalRunConfig(harness="codex")) == []
    assert diff_eval_config(EvalRunConfig(harness="codex"), None) == []
