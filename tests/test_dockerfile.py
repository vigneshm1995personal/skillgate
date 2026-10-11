from __future__ import annotations

import fnmatch
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]


def _dockerignore_patterns() -> list[str]:
    lines: list[str] = []
    for raw in (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append(stripped)
    return lines


def _dockerignored(rel: str, patterns: list[str] | None = None) -> bool:
    """Last matching dockerignore rule wins (Go filepath.Match-ish)."""
    path = rel.strip("/")
    ignored = False
    name = PurePosixPath(path).name
    for pat in patterns or _dockerignore_patterns():
        negate = pat.startswith("!")
        raw = pat[1:] if negate else pat
        directory = raw.endswith("/")
        raw = raw.rstrip("/")
        matched = (
            fnmatch.fnmatch(path, raw)
            or fnmatch.fnmatch(path, raw + "/*")
            or fnmatch.fnmatch(name, raw)
            or path == raw
            or path.startswith(raw + "/")
        )
        if directory and (path == raw or path.startswith(raw + "/")):
            matched = True
        if matched:
            ignored = not negate
    return ignored


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
    assert "COPY web" not in text
    assert "pnpm" not in text.lower()


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


def test_dockerignore_allows_packaged_example_skills() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "COPY skills" in dockerfile
    assert not _dockerignored("skills/pdf/SKILL.md")
    assert not _dockerignored("skills/pdf/evals/cases.yaml")
    assert not _dockerignored("skills/pdf-sabotaged/SKILL.md")
    assert not _dockerignored("skills")


def test_gate_workflow_example_dest_matches_skill_name() -> None:
    text = (ROOT / ".github" / "workflows" / "gate.yml").read_text(encoding="utf-8")
    assert "/tmp/example-pdf" not in text
    assert "skillgate example pdf --dest /tmp/pdf" in text
    assert "skillgate ingest /tmp/pdf" in text
    assert "SKILLGATE_OPENAI_API_KEY" in text
    assert "--key-env" in text

