from __future__ import annotations

import pytest

pytest.importorskip("starlette")

from skillgate_ai.local_guard import hostname_of, origin_is_loopback


def test_hostname_of_handles_ipv6_and_port() -> None:
    assert hostname_of("[::1]:8000") == "::1"
    assert hostname_of("LocalHost:3000") == "localhost"
    assert hostname_of("") == ""


def test_origin_is_loopback() -> None:
    assert origin_is_loopback("http://127.0.0.1:5173") is True
    assert origin_is_loopback("https://evil.example") is False
