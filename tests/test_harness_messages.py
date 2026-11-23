from __future__ import annotations

import pytest

from skillgate_ai.harness.messages import auth_failure_message, usage_limit_message

CLAUDE_SESSION_BANNER = "You've hit your session limit · resets 12:40pm (America/New_York)"


@pytest.mark.parametrize(
    "transcript",
    [
        CLAUDE_SESSION_BANNER,
        "Weekly usage limit reached for this account",
        '{"type":"error","message":"Weekly usage limit reached"}',
        '{"type":"result","is_error":true,"message":"ActionRequiredError: quota"}',
    ],
)
def test_usage_limit_provider_shapes(transcript: str) -> None:
    assert usage_limit_message("", "", transcript) is not None


@pytest.mark.parametrize(
    "transcript",
    [
        "Please set a session limit of 5 retries per user.",
        "The assistant discussed session limits in the help doc.",
        "Use an invalid api key in your config file for testing only.",
        "Tell the user to log in to the portal before continuing.",
        "not logged in",
    ],
)
def test_usage_and_auth_negative_assistant_prose(transcript: str) -> None:
    assert usage_limit_message("", "", transcript) is None
    assert auth_failure_message("", "", transcript) is None


def test_auth_failure_jsonl_error_event() -> None:
    line = '{"type":"error","message":"Error: not logged in. Run auth login."}'
    assert auth_failure_message("", "", line) is not None
    assert auth_failure_message(line, "", "") is not None


def test_auth_failure_stderr_only() -> None:
    assert auth_failure_message("", "authentication required", "") is not None


def test_auth_failure_plain_prose_not_matched() -> None:
    assert auth_failure_message("", "", "Error: not logged in. Run auth login.") is None
