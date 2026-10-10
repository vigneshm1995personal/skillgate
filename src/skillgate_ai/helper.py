"""Mac helper (OSS): connect a Mac to a hosted Skill Gate and run deploy jobs.

Optional add-on — no Skill Gate account required for the rest of the CLI. The
helper only makes OUTBOUND HTTPS calls (polls an authenticated endpoint); it
never listens on a port.
"""

from __future__ import annotations

import io
import json
import os
import plistlib
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from skillgate_ai.deploy import get_adapter
from skillgate_ai.errors import SKILL_CHANGED_MESSAGE, SkillGateError, customer_job_error
from skillgate_ai.ingest import ingest_skill
from skillgate_ai.pack import skill_pack_hash

CONFIG_DIR = Path.home() / ".config" / "skillgate"
CONFIG_PATH = CONFIG_DIR / "helper.json"
LAUNCH_AGENT_LABEL = "com.skillgate-ai.helper"
_MAX_BUNDLE_BYTES = 100 * 1024 * 1024
_MAX_BUNDLE_FILES = 2000
_UNREACHABLE = "Couldn't reach Skill Gate. Try again."
_INSTALL_FAILED = "Couldn't install this skill."


def helper_config_path() -> Path:
    return CONFIG_PATH


def _http_post(url: str, payload: dict, *, headers: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, method="POST", headers=hdrs)
    return _read_json(req, timeout=60)


def _request_error(exc: BaseException) -> SkillGateError:
    if isinstance(exc, urllib.error.HTTPError):
        return SkillGateError(_http_error(exc))
    return SkillGateError(_UNREACHABLE)


def _http_get(url: str, *, headers: dict | None = None) -> bytes:
    req = urllib.request.Request(url, method="GET", headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise _request_error(exc) from exc


def _read_json(req: urllib.request.Request, *, timeout: int) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise _request_error(exc) from exc
    if not body:
        return {}
    try:
        parsed = json.loads(body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        raise SkillGateError(_UNREACHABLE) from exc
    return parsed if isinstance(parsed, dict) else {}


def _http_error(exc: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(exc.read().decode("utf-8"))
        detail = data.get("detail") if isinstance(data, dict) else None
        if isinstance(detail, dict) and detail.get("message"):
            return customer_job_error(str(detail["message"]))
        if isinstance(detail, str):
            return customer_job_error(detail)
    except (OSError, ValueError):
        pass
    return f"Request failed ({exc.code})."


def _require_secure_url(base: str) -> None:
    parsed = urllib.parse.urlparse(base)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}:
        return
    raise SkillGateError("Use an https:// URL for the hosted Skill Gate (the device token is secret).")


def connect(url: str, code: str, name: str | None = None) -> dict:
    """Exchange a one-time pairing code for a device token (stored 0600)."""
    base = (url or "").rstrip("/")
    if not base:
        raise SkillGateError("A hosted Skill Gate URL is required.")
    _require_secure_url(base)
    payload = {"code": code}
    if name:
        payload["name"] = name
    data = _http_post(f"{base}/api/helper/pairing-codes/exchange", payload)
    token = data.get("token")
    device_id = data.get("device_id")
    if not token or not device_id:
        raise SkillGateError("The pairing code was rejected or already used.")
    config = {
        "url": base,
        "token": token,
        "device_id": device_id,
        "name": data.get("name") or name or "Mac",
    }
    path = helper_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2), encoding="utf-8")
    os.chmod(path, 0o600)
    return config


def load_helper_config(path: Path | None = None) -> dict | None:
    target = path or helper_config_path()
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("url") or not data.get("token"):
        return None
    return data


def _auth_headers(config: dict) -> dict:
    return {
        "Authorization": f"Bearer {config['token']}",
        "Content-Type": "application/json",
    }


def _friendly_reason(exc: BaseException) -> str:
    if isinstance(exc, SkillGateError):
        return customer_job_error(exc.message)
    message = str(exc).strip() or exc.__class__.__name__
    return customer_job_error(message[:200]) or _INSTALL_FAILED


def _failed_result(targets: list, error: str) -> dict:
    return {
        "status": "failed",
        "error": error,
        "targets": [
            {"target": t, "status": "failed", "error": error} for t in targets
        ],
    }


def _mismatch_result(targets: list) -> dict:
    return _failed_result(targets, SKILL_CHANGED_MESSAGE)


def _extract_bundle(bundle: bytes, work: Path) -> Path:
    """Extract a bundle defensively: no path traversal, no zip bombs.

    ``zipfile`` sanitizes ``..`` and absolute members on modern Python, but a
    bundle comes from a remote host, so validate each member's resolved target
    stays under ``work`` and cap size / file counts explicitly.
    """
    if len(bundle) > _MAX_BUNDLE_BYTES:
        raise SkillGateError("The skill bundle is too large to install.")
    try:
        with zipfile.ZipFile(io.BytesIO(bundle)) as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_BUNDLE_FILES:
                raise SkillGateError("The skill bundle has too many files.")
            total = 0
            for info in infos:
                total += info.file_size
                try:
                    (work / info.filename).resolve().relative_to(work.resolve())
                except ValueError as exc:
                    raise SkillGateError(
                        "The skill bundle contains an unsafe path."
                    ) from exc
            if total > _MAX_BUNDLE_BYTES:
                raise SkillGateError("The skill bundle expands to too much data.")
            zf.extractall(work)
    except zipfile.BadZipFile as exc:
        raise SkillGateError("The skill bundle is not a valid zip file.") from exc
    return work


def process_job(url: str, config: dict, job: dict) -> dict:
    """Download + verify + install a job. Returns a results payload."""
    job_id = job["id"]
    skill_name = job["skill_name"]
    expected_hash = job.get("skill_md_hash") or ""
    targets = [t for t in (job.get("targets") or []) if t]
    headers = {"Authorization": f"Bearer {config['token']}"}
    mismatch = _mismatch_result(targets)
    bundle = _http_get(f"{url}/api/helper/bundles/{job_id}", headers=headers)
    with tempfile.TemporaryDirectory(prefix="sg-helper-") as td:
        root = Path(td)
        _extract_bundle(bundle, root)
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            return _failed_result(targets, _INSTALL_FAILED)
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _failed_result(targets, _INSTALL_FAILED)
        if manifest.get("skill_md_hash") != expected_hash:
            return mismatch
        skill_dir = root / skill_name
        if not skill_dir.is_dir() or skill_pack_hash(skill_dir) != expected_hash:
            return mismatch
        try:
            loaded = ingest_skill(skill_dir)
        except SkillGateError as exc:
            return _failed_result(targets, _friendly_reason(exc))
        results: list[dict] = []
        failed = False
        for target in targets:
            try:
                get_adapter(target).install(skill=loaded, source=skill_dir)
                results.append({"target": target, "status": "installed"})
            except SkillGateError as exc:
                failed = True
                results.append(
                    {"target": target, "status": "failed", "error": _friendly_reason(exc)}
                )
            except Exception as exc:  # noqa: BLE001 — surfaced as a friendly reason
                failed = True
                results.append(
                    {"target": target, "status": "failed", "error": _friendly_reason(exc)}
                )
        return {"status": "installed" if not failed else "failed", "targets": results}


def run_helper(config: dict, *, once: bool = False, sleep_sec: int = 5) -> None:
    """Poll for jobs (outbound only), run them, report results."""
    url = config["url"].rstrip("/")
    headers = _auth_headers(config)
    while True:
        try:
            polled = _http_post(f"{url}/api/helper/poll", {}, headers=headers)
        except SkillGateError:
            polled = {}
        job = polled.get("job") if isinstance(polled, dict) else None
        if job:
            try:
                result = process_job(url, config, job)
            except SkillGateError as exc:
                result = _failed_result(
                    job.get("targets") or [], _friendly_reason(exc)
                )
            try:
                _http_post(f"{url}/api/helper/results/{job['id']}", result, headers=headers)
            except SkillGateError:
                pass
        if once:
            return
        time.sleep(max(1, sleep_sec))


def install_launchd_plist() -> Path:
    """Write a macOS LaunchAgent that runs ``skillgate helper`` hands-off."""
    if sys.platform != "darwin":
        raise SkillGateError("LaunchAgent autostart is macOS-only.")
    binary = shutil.which("skillgate") or "skillgate"
    plist = {
        "Label": LAUNCH_AGENT_LABEL,
        "RunAtLoad": True,
        "KeepAlive": False,
        "ProgramArguments": [binary, "helper"],
    }
    launch_dir = Path.home() / "Library" / "LaunchAgents"
    launch_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(launch_dir, 0o755)
    except OSError:
        pass
    dest = launch_dir / f"{LAUNCH_AGENT_LABEL}.plist"
    with open(dest, "wb") as handle:
        plistlib.dump(plist, handle)
    os.chmod(dest, 0o644)
    return dest
