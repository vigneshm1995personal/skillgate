from __future__ import annotations

import pytest

from skillgate_ai.harness.messages import auth_failure_message, usage_limit_message


@pytest.mark.parametrize(
    "transcript",
    [
        "You've hit your session limit · resets 12:40pm (America/New_York)",
        "Weekly usage limit reached for this account",
    ],
)
def test_usage_limit_claude_and_cursor_transcript_shapes(transcript: str) -> None:
    assert usage_limit_message("", "", transcript) is not None


def test_auth_failure_in_transcript() -> None:
    assert auth_failure_message("", "", "Error: not logged in. Run auth login.") is not None
