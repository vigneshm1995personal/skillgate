from __future__ import annotations

import http.client
import io
import json
import os
import plistlib
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import pytest

from skillgate_ai import helper as helper_mod
from skillgate_ai.errors import SKILL_CHANGED_MESSAGE, SkillGateError, customer_job_error
from skillgate_ai.helper import connect, install_launchd_plist, process_job, run_helper
from skillgate_ai.http_retry import RetryableStatus
from skillgate_ai.pack import copy_skill_pack, skill_pack_hash


def _write_skill(folder: Path, name: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        "description: A helper skill. Use when verifying installing.\n"
        "---\n\n"
        f"# {name}\n",
        encoding="utf-8",
    )
    (folder / "scripts").mkdir()
    (folder / "scripts" / "run.py").write_text("print('ok')\n", encoding="utf-8")
    return folder


def _bundle(skill_dir: Path, name: str, manifest_hash: str) -> bytes:
    manifest = {
        "version": 1,
        "skill_name": name,
        "semver": "0.1",
        "skill_md_hash": manifest_hash,
        "file_count": 0,
        "files": [],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(skill_dir.rglob("*")):
            if path.is_file():
                zf.write(path, arcname=f"{name}/{path.relative_to(skill_dir).as_posix()}")
        zf.writestr("manifest.json", json.dumps(manifest))
    return buffer.getvalue()


def test_connect_rejects_insecure_remote_url() -> None:
    with pytest.raises(SkillGateError, match="https"):
        connect("http://evil.example", "CODE1234")


def test_load_helper_config_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "helper.json"
    path.write_text("not-json", encoding="utf-8")
    assert helper_mod.load_helper_config(path) is None


def test_friendly_reason_maps_skill_gate_error() -> None:
    msg = helper_mod._friendly_reason(SkillGateError("skill_md hash mismatch"))
    assert "changed" in msg.lower()


def test_connect_writes_0600_helper_json(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "helper.json"
    monkeypatch.setattr(helper_mod, "CONFIG_PATH", target)
    monkeypatch.setattr(
        helper_mod,
        "_http_post",
        lambda url, payload, **kwargs: {
            "token": "tok",
            "device_id": "dev-1",
            "name": "My Mac",
        },
    )
    config = connect("https://host.example", "ABC12345", "My Mac")
    assert config["url"] == "https://host.example"
    assert config["token"] == "tok"
    assert target.is_file()
    assert os.stat(target).st_mode & 0o777 == 0o600
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["url"] == "https://host.example"
    assert data["token"] == "tok"
    assert data["device_id"] == "dev-1"


def test_helper_hash_mismatch_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_root: Path
) -> None:
    skill_dir = _write_skill(tmp_path / "pdf", "pdf")
    correct_hash = skill_pack_hash(skill_dir)
    monkeypatch.setattr(
        helper_mod, "_http_get", lambda url, **kwargs: _bundle(skill_dir, "pdf", "WRONG")
    )
    config = {"url": "https://host.example", "token": "tok"}
    job = {
        "id": "j1",
        "skill_name": "pdf",
        "skill_md_hash": correct_hash,
        "targets": ["cursor"],
    }
    result = process_job("https://host.example", config, job)
    assert result["status"] == "failed"
    assert result["targets"][0]["status"] == "failed"
    assert result["targets"][0]["error"] == SKILL_CHANGED_MESSAGE
    assert "version mismatch" not in result["targets"][0]["error"]
    assert "WRONG" not in json.dumps(result)
    assert not (Path(os.environ["SKILLGATE_CURSOR_SKILLS"]) / "pdf").exists()


def test_helper_verifies_goldens_in_recorded_hash(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_root: Path
) -> None:
    """Passes recorded with evals/goldens still verify; editor install omits goldens."""
    skill_dir = _write_skill(tmp_path / "csv-clean", "csv-clean")
    goldens = skill_dir / "evals" / "goldens"
    goldens.mkdir(parents=True)
    (goldens / "clean-messy.csv").write_text("item,amount\nalpha,1\n", encoding="utf-8")
    recorded = skill_pack_hash(skill_dir)
    skipped = tmp_path / "skipped" / "csv-clean"
    copy_skill_pack(skill_dir, skipped)
    assert skill_pack_hash(skipped) != recorded
    monkeypatch.setattr(
        helper_mod,
        "_http_get",
        lambda url, **kwargs: _bundle(skill_dir, "csv-clean", recorded),
    )
    config = {"url": "https://host.example", "token": "tok"}
    job = {
        "id": "j1",
        "skill_name": "csv-clean",
        "skill_md_hash": recorded,
        "targets": ["cursor"],
    }
    result = process_job("https://host.example", config, job)
    assert result["status"] == "installed"
    installed = Path(os.environ["SKILLGATE_CURSOR_SKILLS"]) / "csv-clean"
    assert (installed / "SKILL.md").is_file()
    assert (installed / "scripts" / "run.py").is_file()
    assert not (installed / "evals" / "goldens").exists()


def test_helper_refuses_red_latest_check(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_root: Path
) -> None:
    from skillgate_ai.history import append_eval

    skill_dir = _write_skill(tmp_path / "pdf", "pdf")
    append_eval(skill_dir, run_id="red", passed=False)
    correct_hash = skill_pack_hash(skill_dir)
    monkeypatch.setattr(
        helper_mod,
        "_http_get",
        lambda url, **kwargs: _bundle(skill_dir, "pdf", correct_hash),
    )
    config = {"url": "https://host.example", "token": "tok"}
    job = {
        "id": "j1",
        "skill_name": "pdf",
        "skill_md_hash": correct_hash,
        "targets": ["cursor"],
    }
    result = process_job("https://host.example", config, job)
    assert result["status"] == "failed"
    assert "did not pass" in result["targets"][0]["error"]
    assert not (Path(os.environ["SKILLGATE_CURSOR_SKILLS"]) / "pdf").exists()


def test_helper_failed_copy_leaves_existing_install(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_root: Path
) -> None:
    skill_dir = _write_skill(tmp_path / "pdf", "pdf")
    correct_hash = skill_pack_hash(skill_dir)
    dest = Path(os.environ["SKILLGATE_CURSOR_SKILLS"]) / "pdf"
    dest.mkdir(parents=True)
    marker = dest / "KEEP.txt"
    marker.write_text("old-install", encoding="utf-8")
    monkeypatch.setattr(
        helper_mod,
        "_http_get",
        lambda url, **kwargs: _bundle(skill_dir, "pdf", correct_hash),
    )

    def boom(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr("skillgate_ai.pack.tree.shutil.copytree", boom)
    result = process_job(
        "https://host.example",
        {"url": "https://host.example", "token": "tok"},
        {
            "id": "j1",
            "skill_name": "pdf",
            "skill_md_hash": correct_hash,
            "targets": ["cursor"],
        },
    )
    assert result["status"] == "failed"
    assert marker.is_file()
    assert marker.read_text(encoding="utf-8") == "old-install"


def test_helper_installs_and_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, project_root: Path
) -> None:
    skill_dir = _write_skill(tmp_path / "pdf", "pdf")
    correct_hash = skill_pack_hash(skill_dir)
    monkeypatch.setattr(
        helper_mod,
        "_http_get",
        lambda url, **kwargs: _bundle(skill_dir, "pdf", correct_hash),
    )
    config = {"url": "https://host.example", "token": "tok"}
    job = {
        "id": "j1",
        "skill_name": "pdf",
        "skill_md_hash": correct_hash,
        "targets": ["cursor"],
    }
    result = process_job("https://host.example", config, job)
    assert result["status"] == "installed"
    assert result["targets"] == [{"target": "cursor", "status": "installed"}]
    assert (Path(os.environ["SKILLGATE_CURSOR_SKILLS"]) / "pdf" / "SKILL.md").is_file()


def test_helper_install_launchd_plist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    home = tmp_path
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.setattr(helper_mod.sys, "platform", "darwin")
    dest = install_launchd_plist()
    assert dest.is_file()
    plist = plistlib.loads(dest.read_bytes())
    assert plist["RunAtLoad"] is True
    assert plist["ProgramArguments"][-1] == "helper"
    assert os.stat(dest).st_mode & 0o777 == 0o644


def test_helper_install_launchd_plist_non_mac(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(helper_mod.sys, "platform", "linux")
    with pytest.raises(helper_mod.SkillGateError):
        install_launchd_plist()


def test_customer_job_error_hides_hashes() -> None:
    leaked = "Skill hash mismatch while building bundle: 961b02b6 != efca8b89."
    assert customer_job_error(leaked) == SKILL_CHANGED_MESSAGE
    assert "961b02b6" not in customer_job_error(leaked)
    assert customer_job_error("version mismatch") == SKILL_CHANGED_MESSAGE


def test_http_get_wraps_urlerror(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(helper_mod, "_urlopen", boom)
    with pytest.raises(helper_mod.SkillGateError) as exc:
        helper_mod._http_get("https://host.example/bundle")
    assert exc.value.message == helper_mod._UNREACHABLE
    assert "timed out" not in exc.value.message
    assert "URLError" not in exc.value.message


def test_read_json_wraps_bad_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        def read(self) -> bytes:
            return b"not-json{"

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args) -> bool:
            return False

    monkeypatch.setattr(helper_mod, "_urlopen", lambda *args, **kwargs: _Resp())
    req = urllib.request.Request("https://host.example/poll", method="GET")
    with pytest.raises(helper_mod.SkillGateError) as exc:
        helper_mod._read_json(req, timeout=1)
    assert exc.value.message == helper_mod._UNREACHABLE


def test_http_get_wraps_incomplete_read(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Resp:
        def read(self) -> bytes:
            raise http.client.IncompleteRead(b"abc", 100)

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args) -> bool:
            return False

    monkeypatch.setattr(helper_mod, "_urlopen", lambda *args, **kwargs: _Resp())
    with pytest.raises(helper_mod.SkillGateError) as exc:
        helper_mod._http_get("https://host.example/bundle")
    assert exc.value.message == helper_mod._UNREACHABLE
    assert "IncompleteRead" not in exc.value.message


def test_run_helper_reports_network_error_after_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reported: list[dict] = []

    def fake_post(url, payload, **kwargs):
        if url.endswith("/api/helper/poll"):
            return {
                "job": {
                    "id": "j1",
                    "skill_name": "pdf",
                    "skill_md_hash": "abc",
                    "targets": ["cursor"],
                }
            }
        reported.append(payload)
        return {}

    def boom(*args, **kwargs):
        raise urllib.error.URLError("timed out")

    monkeypatch.setattr(helper_mod, "_http_post", fake_post)
    monkeypatch.setattr(helper_mod, "_urlopen", boom)
    run_helper({"url": "https://host.example", "token": "tok"}, once=True)
    assert reported
    assert reported[0]["status"] == "failed"
    blob = json.dumps(reported[0])
    assert "timed out" not in blob
    assert "URLError" not in blob
    assert "Couldn't reach Skill Gate" in reported[0]["error"]


def test_run_helper_reports_incomplete_read_after_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reported: list[dict] = []

    def fake_post(url, payload, **kwargs):
        if url.endswith("/api/helper/poll"):
            return {
                "job": {
                    "id": "j1",
                    "skill_name": "pdf",
                    "skill_md_hash": "abc",
                    "targets": ["cursor"],
                }
            }
        reported.append(payload)
        return {}

    class _Resp:
        def read(self) -> bytes:
            raise http.client.IncompleteRead(b"abc", 100)

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *args) -> bool:
            return False

    monkeypatch.setattr(helper_mod, "_http_post", fake_post)
    monkeypatch.setattr(helper_mod, "_urlopen", lambda *args, **kwargs: _Resp())
    run_helper({"url": "https://host.example", "token": "tok"}, once=True)
    assert reported
    assert reported[0]["status"] == "failed"
    blob = json.dumps(reported[0])
    assert "IncompleteRead" not in blob
    assert "Couldn't reach Skill Gate" in reported[0]["error"]


def test_connect_config_dir_is_0700(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "cfg" / "helper.json"
    monkeypatch.setattr(helper_mod, "CONFIG_PATH", target)
    monkeypatch.setattr(
        helper_mod,
        "_http_post",
        lambda url, payload, **kwargs: {
            "token": "tok",
            "device_id": "dev-1",
            "name": "My Mac",
        },
    )
    connect("https://host.example", "ABC12345")
    assert target.parent.is_dir()
    assert os.stat(target.parent).st_mode & 0o777 == 0o700


def test_exchange_post_not_retried_on_503(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "helper.json"
    monkeypatch.setattr(helper_mod, "CONFIG_PATH", target)
    calls = {"n": 0}

    def flaky(_req, **kwargs):
        calls["n"] += 1
        raise RetryableStatus(503)

    monkeypatch.setattr(helper_mod, "_urlopen", flaky)
    with pytest.raises(helper_mod.SkillGateError):
        connect("https://host.example", "ABC12345")
    assert calls["n"] == 1


def test_poll_post_not_retried_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def flaky(_req, **kwargs):
        calls["n"] += 1
        raise RetryableStatus(503)

    monkeypatch.setattr(helper_mod, "_urlopen", flaky)
    run_helper({"url": "https://host.example", "token": "tok"}, once=True)
    assert calls["n"] == 1


def test_results_post_retries_on_503(monkeypatch: pytest.MonkeyPatch) -> None:
    result_attempts = {"n": 0}
    monkeypatch.setattr("skillgate_ai.http_retry.sleep", lambda _s: None)

    job = {
        "id": "j1",
        "skill_name": "pdf",
        "skill_md_hash": "abc",
        "targets": [],
    }

    def flaky(req, **kwargs):
        if req.full_url.endswith("/api/helper/poll"):
            payload = json.dumps({"job": job}).encode("utf-8")

            class _Poll:
                def read(self) -> bytes:
                    return payload

                def __enter__(self) -> _Poll:
                    return self

                def __exit__(self, *args) -> bool:
                    return False

            return _Poll()
        if "/api/helper/results/" in req.full_url:
            result_attempts["n"] += 1
            if result_attempts["n"] < 3:
                raise RetryableStatus(503)

            class _Ok:
                def read(self) -> bytes:
                    return b"{}"

                def __enter__(self) -> _Ok:
                    return self

                def __exit__(self, *args) -> bool:
                    return False

            return _Ok()
        raise AssertionError(f"unexpected url {req.full_url}")

    monkeypatch.setattr(helper_mod, "_urlopen", flaky)
    monkeypatch.setattr(
        helper_mod, "process_job", lambda *args, **kwargs: {"status": "installed", "targets": []}
    )
    run_helper({"url": "https://host.example", "token": "tok"}, once=True)
    assert result_attempts["n"] == 3


def test_redirect_strips_authorization_cross_origin() -> None:
    handler = helper_mod._StripAuthRedirectHandler()
    req = urllib.request.Request(
        "https://host.example/start",
        headers={"Authorization": "Bearer secret-token"},
        method="GET",
    )

    class _Resp:
        status = 302
        headers = {"Location": "http://other.example/path"}

    new_req = handler.redirect_request(req, None, 302, "Found", {}, "http://other.example/path")
    assert new_req is not None
    lowered = {k.lower(): v for k, v in new_req.header_items()}
    assert "authorization" not in lowered


def test_redirect_keeps_authorization_same_origin() -> None:
    handler = helper_mod._StripAuthRedirectHandler()
    req = urllib.request.Request(
        "https://host.example/start",
        headers={"Authorization": "Bearer secret-token"},
        method="GET",
    )

    class _Resp:
        status = 302
        headers = {"Location": "https://host.example/other"}

    new_req = handler.redirect_request(req, None, 302, "Found", {}, "https://host.example/other")
    assert new_req is not None
    lowered = {k.lower(): v for k, v in new_req.header_items()}
    assert lowered.get("authorization") == "Bearer secret-token"
