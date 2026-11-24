from __future__ import annotations

from skillgate_ai.redact import redact_harness_text, tail_text

SECRET = "sk-liveabcdefghijklmnopqrstuvwxyz123456"
JWT = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
)


def test_redact_harness_text_known_secret() -> None:
    blob = f"failed with {SECRET} in output"
    cleaned = redact_harness_text(blob, known=SECRET)
    assert SECRET not in cleaned
    assert "***" in cleaned


def test_redact_harness_text_sk_prefix() -> None:
    cleaned = redact_harness_text(f"key={SECRET}")
    assert SECRET not in cleaned


def test_redact_harness_text_jwt() -> None:
    cleaned = redact_harness_text(f"Authorization: Bearer {JWT}")
    assert JWT not in cleaned


def test_redact_harness_text_authorization_header() -> None:
    cleaned = redact_harness_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz1234")
    assert "abcdefghijklmnopqrstuvwxyz1234" not in cleaned


def test_redact_harness_text_cred_pair() -> None:
    cleaned = redact_harness_text("token=supersecretvalue123456789012345")
    assert "supersecretvalue" not in cleaned


def test_tail_text_redacts_before_truncation() -> None:
    line = f"not logged in {SECRET}"
    tail = tail_text("\n".join([line] * 30), known=SECRET, max_lines=5)
    assert SECRET not in tail


def test_redact_crsr_underscore_token() -> None:
    secret = "deadbeef1234567890"
    token = f"crsr_{secret}"
    cleaned = redact_harness_text(f"login failed: {token}")
    assert secret not in cleaned
    assert token not in cleaned
    assert "crsr_***" in cleaned


def test_redact_key_underscore_token() -> None:
    secret = "deadbeef1234567890"
    token = f"key_{secret}"
    cleaned = redact_harness_text(f"bad {token}")
    assert secret not in cleaned
    assert token not in cleaned
    assert "key_***" in cleaned
