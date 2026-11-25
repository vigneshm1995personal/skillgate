from __future__ import annotations

import socket
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from skillgate_ai.errors import SkillGateError
from skillgate_ai.server import (
    _ensure_port_free,
    _port_has_listener,
    _socket_family,
    attach_static,
    web_static_dir,
)


def test_socket_family_ipv6_and_ipv4() -> None:
    assert _socket_family("::1") == socket.AF_INET6
    assert _socket_family("127.0.0.1") == socket.AF_INET


def test_port_has_listener_on_free_port() -> None:
    assert _port_has_listener("127.0.0.1", 9) is False


def test_web_static_dir_finds_packaged_or_repo_dist(monkeypatch: pytest.MonkeyPatch) -> None:
    assert web_static_dir() is not None


def test_attach_static_serves_index(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("ok", encoding="utf-8")
    app = FastAPI()
    attach_static(app, dist=dist)
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "ok"


def test_attach_static_missing_dist_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.server.web_static_dir", lambda: None)
    app = FastAPI()
    attach_static(app, dist=None)
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 503
    assert "not built" in response.text.lower()


def test_ensure_port_free_raises_when_listener_present(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "skillgate_ai.server._port_has_listener",
        lambda host, port, timeout=0.25: True,
    )
    with pytest.raises(SkillGateError, match="already in use"):
        _ensure_port_free("127.0.0.1", 8765)
