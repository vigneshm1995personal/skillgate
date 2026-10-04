from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

from skillgate_ai.demo_files import ensure_demo_pdfs
from skillgate_ai.local_ui.server import start_background


def _request(method: str, url: str, body: dict | None = None) -> tuple[int, dict | str]:
    data = None
    headers = {"Content-Type": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8")
            parsed: dict | str
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = raw
            return resp.status, parsed
    except urllib.error.HTTPError as orig:
        raw = orig.read().decode("utf-8")
        try:
            parsed = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            parsed = raw
        return orig.code, parsed


def _poll_run(base: str, run_id: str, *, timeout: float = 120.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, payload = _request("GET", f"{base}/api/runs/{run_id}")
        assert status == 200, payload
        assert isinstance(payload, dict)
        if payload.get("exit_code") is not None:
            return payload
        time.sleep(0.2)
    raise AssertionError(f"run {run_id} did not finish")


def test_ui_meta_no_account(project_root: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, payload = _request("GET", f"{base}/api/meta")
        assert status == 200
        assert payload["account"] is False
        assert payload["has_any_key"] is False
        assert payload["demo_default"] is True
    finally:
        server.shutdown()
        server.server_close()


def test_ui_static_index(project_root: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        req = urllib.request.Request(base + "/")
        with urllib.request.urlopen(req, timeout=10) as resp:
            html = resp.read().decode("utf-8")
        assert resp.status == 200
        assert "no account" in html.lower()
        assert "Skill Gate" in html
    finally:
        server.shutdown()
        server.server_close()


def test_ui_name_mismatch_400(project_root: Path, tmp_path: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, payload = _request(
            "POST",
            f"{base}/api/packs",
            {"parent": str(tmp_path), "name": "my-skill", "folder": "other"},
        )
        assert status == 400, payload
        assert "must match" in str(payload).lower()
        assert "rename the folder or the `name` field so they match" in str(payload).lower()
    finally:
        server.shutdown()
        server.server_close()


def test_ui_check_sabotaged_json(project_root: Path, tmp_path: Path) -> None:
    dest = tmp_path / "pdf-sabotaged"
    shutil.copytree(project_root / "skills" / "pdf-sabotaged", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, started = _request("POST", f"{base}/api/check", {"path": str(dest)})
        assert status == 202, started
        assert started["exit_code"] is None
        done = _poll_run(base, started["run_id"])
        report = done["report"]
        assert done["exit_code"] == 1
        assert report["gate"] == "red"
        assert report["passed_count"] == 1
        paste = (report.get("advice") or {}).get("paste") or ""
        assert "grocery" not in paste.lower()
        assert "dinner" not in paste.lower()
        assert "pdf" in paste.lower()
    finally:
        server.shutdown()
        server.server_close()


def test_ui_apply_fix_then_green(project_root: Path, tmp_path: Path) -> None:
    dest = tmp_path / "pdf-sabotaged"
    shutil.copytree(project_root / "skills" / "pdf-sabotaged", dest)
    ensure_demo_pdfs(dest / "evals" / "fixtures")
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        _, started = _request("POST", f"{base}/api/check", {"path": str(dest)})
        red = _poll_run(base, started["run_id"])
        advice = (red["report"] or {}).get("advice") or {}
        description = advice.get("description") or advice.get("paste")
        status, applied = _request(
            "POST",
            f"{base}/api/pack/apply-advice",
            {"path": str(dest), "description": description},
        )
        assert status == 200, applied
        _, started2 = _request("POST", f"{base}/api/check", {"path": str(dest)})
        green = _poll_run(base, started2["run_id"])
        assert green["exit_code"] == 0, green
        assert green["report"]["gate"] == "green"
    finally:
        server.shutdown()
        server.server_close()


def test_ui_new_pack_no_key_green(project_root: Path, tmp_path: Path) -> None:
    server, base, _state = start_background(root=project_root, host="127.0.0.1", port=0)
    try:
        status, created = _request(
            "POST",
            f"{base}/api/packs",
            {"parent": str(tmp_path), "name": "doc-notes"},
        )
        assert status == 201, created
        _, started = _request("POST", f"{base}/api/check", {"path": created["path"]})
        done = _poll_run(base, started["run_id"])
        assert done["exit_code"] == 0, done
        assert done["report"]["gate"] == "green"
    finally:
        server.shutdown()
        server.server_close()
