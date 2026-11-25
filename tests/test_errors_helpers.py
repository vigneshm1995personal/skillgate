from __future__ import annotations

import subprocess

import pytest
from pydantic import BaseModel, Field, ValidationError

from skillgate_ai.errors import (
    HarnessError,
    SkillGateError,
    agent_timeout_error,
    customer_job_error,
    error_payload,
    friendly_http_status,
    friendly_os_error,
    friendly_validation_error,
    harness_http_error,
    timeout_harness_error,
)


def test_customer_job_error_sanitizes_hashes_and_internal_paths() -> None:
    assert "changed" in customer_job_error("skill_md hash mismatch").lower()
    assert customer_job_error("/root/skillgate_crash abcdef01") == "Couldn't install this skill."
    assert customer_job_error("plain message") == "plain message"


def test_error_payload_includes_auth_diagnostics() -> None:
    exc = HarnessError("fail", diagnostics={"logged_in": False})
    payload = error_payload(exc)
    assert payload["auth_diagnostics"]["logged_in"] is False


def test_agent_and_timeout_harness_errors() -> None:
    err = agent_timeout_error(30)
    assert "timed out" in err.message.lower()
    err2 = timeout_harness_error(subprocess.TimeoutExpired(cmd="agent", timeout=15), timeout_sec=15)
    assert err2 is not None
    assert "15" in (err2.hint or "")


def test_friendly_os_error_maps_errno() -> None:
    assert "read file" in friendly_os_error(PermissionError(13, "nope"), what="read file").lower()


def test_harness_http_error_openai_flag() -> None:
    err = harness_http_error(401, openai=True)
    assert err.message
    assert friendly_http_status(429, openai=False)


def test_skill_gate_error_render_includes_hint() -> None:
    exc = SkillGateError("main", hint="try again")
    assert "try again" in exc.render()


class _BudgetRow(BaseModel):
    max_steps: int = Field(gt=0)


def test_friendly_validation_error_formats_pydantic() -> None:
    try:
        _BudgetRow(max_steps=0)
    except ValidationError as exc:
        msg = friendly_validation_error(exc, kind="budget")
        assert msg and "max_steps" in msg.lower()
    else:
        pytest.fail("expected validation error")


def test_friendly_validation_error_case_pack_labels() -> None:
    from skillgate_ai.case_pack.models import CasePack

    raw = {"schema": 99, "skill": "pdf", "cases": []}
    try:
        CasePack.model_validate(raw)
    except ValidationError as exc:
        msg = friendly_validation_error(exc, kind="Case pack", raw=raw)
        assert "checks" in msg.lower()
    else:
        pytest.fail("expected validation error")
