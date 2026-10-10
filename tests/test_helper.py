from __future__ import annotations

import io
import json
import os
import plistlib
import zipfile
from pathlib import Path

import pytest

from skillgate_ai import helper as helper_mod
from skillgate_ai.errors import SKILL_CHANGED_MESSAGE, customer_job_error
from skillgate_ai.helper import connect, install_launchd_plist, process_job
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


def test_connect_writes_0600_helper_json(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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


def test_helper_install_launchd_plist(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
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
