from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_dockerfile_is_cli_not_serve() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert text.splitlines()[0] == "# syntax=docker/dockerfile:1"
    assert 'ENTRYPOINT ["skillgate"]' in text
    assert 'CMD ["check", "/pack"]' in text
    assert "serve" not in text.lower()
    assert "EXPOSE" not in text
    assert "USER appuser" in text
    assert "--chown=1001:1001" in text
    assert "python:3.12-slim-bookworm@sha256:" in text
    for needle in ("TOKEN", "SECRET", "PASSWORD", "SKILLGATE_SECRETS_KEY"):
        assert f"ARG {needle}" not in text
        assert f"ENV {needle}" not in text
    assert "COPY .env" not in text
    assert "COPY .pypirc" not in text


def test_compose_and_dockerignore_exist() -> None:
    assert (ROOT / "compose.yaml").is_file()
    ignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    assert ".env" in ignore
    assert "db-creds.env" in ignore
    assert "**/.npmrc" in ignore


def test_compose_has_no_ui_ports() -> None:
    text = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    assert "ports:" not in text
    assert "check /pack" in text
    assert "8477" not in text
    assert "8765" not in text

