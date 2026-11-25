from __future__ import annotations

from pathlib import Path

from skillgate_ai.api_payloads import (
    _deploy_payload,
    _gate_source_run,
    _neutral_scored_by,
    is_relative,
    scrub_config,
)
from skillgate_ai.judge_copy import SCORED_BY_JUDGE


def test_neutral_scored_by_strips_leaky_vendor_text() -> None:
    text = "Something went wrong with openai decisions."
    assert _neutral_scored_by(text, None) == SCORED_BY_JUDGE


def test_neutral_scored_by_uses_display_name_stamp() -> None:
    text = "Scored by something openai-ish."
    stamp = {"display_name": "My Judge", "provider": "custom"}
    assert _neutral_scored_by(text, stamp).startswith("Scored by My Judge")


def test_neutral_scored_by_couldnt_with_leaky_reason() -> None:
    text = "openai couldn't finish scoring."
    assert _neutral_scored_by(text, None) == "The judge couldn't score this run."


def test_scrub_config_drops_internal_keys_for_demo_harness() -> None:
    raw = {
        "harness": "demo",
        "model": "secret-model",
        "config_label_raw": "x",
        "judge": {"model": "m", "display_name": "J", "backend": "b"},
    }
    cleaned = scrub_config(raw)
    assert cleaned is not None
    assert "model" not in cleaned
    assert "config_label_raw" not in cleaned
    assert "display_name" in cleaned["judge"]


def test_scrub_config_keeps_live_agent_model() -> None:
    raw = {"harness": "codex", "model": "gpt-5", "applied": {"via_gateway": True, "model": True}}
    cleaned = scrub_config(raw)
    assert cleaned is not None
    assert cleaned["model"] == "gpt-5"
    assert "via_gateway" not in (cleaned.get("applied") or {})


def test_deploy_payload_labels_target() -> None:
    row = {"target": "cursor-agent", "status": "installed", "ts": "t", "file_count": 3}
    payload = _deploy_payload(row, index=0)
    assert "skills folder" in payload["dest_label"]
    assert payload["id"] == 1


def test_gate_source_run_matches_run_id() -> None:
    hist = [{"run_id": "r1", "passed": True}]
    runs = [{"id": "r1", "status": "done"}, {"id": "r2", "status": "done"}]
    assert _gate_source_run(runs, hist) == runs[0]
    assert _gate_source_run(runs, [{"run_id": "missing"}]) is None


def test_is_relative_under_root() -> None:
    root = Path("/tmp/root")
    assert is_relative(root / "a", root) is True
    assert is_relative(Path("/etc/passwd"), root) is False
