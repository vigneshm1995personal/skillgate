"""Install skillgate-ai and run ``skillgate check`` for the composite action.

Exit 0 passes, 1 fails, and 2 means the check cannot run. A ``judge`` value is
one decision model: a rejected id does not switch to another model, and the
check does not run.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import urllib.request

PYPI_JSON = "https://pypi.org/pypi/skillgate-ai/json"
_VERSION = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.*+!_-]*$")
_SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")
_CHAT = frozenset({"chat", "completions", "responses", "structured"})
_REMOVED = frozenset({"other", "compatible", "aws", "unknown"})
_NOT_DECISION = frozenset({"auto", "skip"})
_CHAT_MSG = (
    "A decision model scores checks directly. "
    "Chat and Responses completion models are not judges."
)
_REMOVED_MSG = "That scoring setup was removed. Pick a decision model."
_NOT_MSG = "That is not a decision model. Pick a registered decision model."


class ActionError(Exception):
    """The action cannot run. The process exits 2."""


def main() -> int:
    mask_skillgate_secrets()
    try:
        version = resolve_version(os.environ.get("INPUT_VERSION", ""))
        install_release(version)
    except ActionError as exc:
        return finish(2, str(exc))
    judge = os.environ.get("INPUT_JUDGE", "").strip()
    if judge:
        rejected = reject_judge(judge)
        if rejected:
            return finish(2, rejected)
        code, detail = run_command(judge_command(judge))
        if code != 0:
            return finish(2, detail)
    code, detail = run_command(check_command())
    return finish(code, detail)


def resolve_version(raw: str) -> str:
    version = raw.strip()
    if version in {"", "latest"}:
        version = fetch_latest_version()
    if not _VERSION.fullmatch(version):
        raise ActionError(f"Invalid skillgate-ai version: {version!r}.")
    return version


def fetch_latest_version() -> str:
    try:
        with urllib.request.urlopen(PYPI_JSON, timeout=30) as response:
            payload = json.load(response)
        version = str(payload["info"]["version"]).strip()
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ActionError("Could not read the latest skillgate-ai release.") from exc
    if not _VERSION.fullmatch(version):
        raise ActionError("Could not read the latest skillgate-ai release.")
    return version


def pip_install_args(version: str) -> list[str]:
    return [f"skillgate-ai=={version}"]


def install_release(version: str) -> None:
    cmd = [sys.executable, "-m", "pip", "install", *pip_install_args(version)]
    print(f"Installing skillgate-ai=={version}", flush=True)
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        raise ActionError(f"Could not install skillgate-ai=={version}.")


def reject_judge(judge: str) -> str | None:
    name = judge.strip().lower()
    if name in _CHAT:
        return _CHAT_MSG
    if name in _REMOVED:
        return _REMOVED_MSG
    if name in _NOT_DECISION:
        return _NOT_MSG
    return None


def judge_command(judge: str) -> list[str]:
    cmd = ["skillgate", "judge", "provider", "set", judge]
    model = os.environ.get("INPUT_MODEL", "").strip()
    base_url = os.environ.get("INPUT_BASE_URL", "").strip()
    account_id = os.environ.get("INPUT_ACCOUNT_ID", "").strip()
    if model:
        cmd.extend(["--model", model])
    if base_url:
        cmd.extend(["--base-url", base_url])
    if account_id:
        cmd.extend(["--account-id", account_id])
    return cmd


def check_command() -> list[str]:
    path = os.environ.get("INPUT_PATH", "").strip() or "skills"
    cmd = ["skillgate", "check", path]
    harness = os.environ.get("INPUT_HARNESS", "").strip()
    if harness:
        cmd.extend(["--harness", harness])
    user_args = shlex.split(os.environ.get("INPUT_ARGS", ""))
    cmd.extend(user_args)
    if not any(arg == "--summary" or arg.startswith("--summary=") for arg in user_args):
        cmd.extend(["--summary", "github"])
    return cmd


def run_command(cmd: list[str]) -> tuple[int, str]:
    try:
        completed = subprocess.run(cmd, check=False, text=True, capture_output=True)
    except FileNotFoundError:
        return 2, f"Could not run {cmd[0]}."
    _write(sys.stdout, completed.stdout)
    _write(sys.stderr, completed.stderr)
    detail = "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part and part.strip()
    )
    return completed.returncode, detail


def finish(code: int, detail: str = "") -> int:
    print(status_line(code), flush=True)
    write_summary(code, detail)
    write_output(code, detail)
    return code


def status_line(code: int) -> str:
    if code == 0:
        return "Skill Gate passed (exit 0)."
    if code == 1:
        return "Skill Gate failed (exit 1)."
    if code == 2:
        return "Skill Gate cannot run (exit 2)."
    return f"Skill Gate exited {code}."


def result_name(code: int) -> str:
    return {0: "pass", 1: "fail", 2: "cannot-run"}.get(code, "error")


def write_summary(code: int, detail: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if not path:
        return
    heading = {0: "Passed", 1: "Failed", 2: "Cannot run"}.get(code, "Exited")
    lines = ["## Skill Gate", "", f"**{heading}** (exit {code})."]
    public = redact(detail).strip()
    if public:
        lines.extend(["", public])
    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def write_output(code: int, detail: str = "") -> None:
    path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not path:
        return
    first = ""
    public = redact(detail).strip()
    if public:
        first = public.splitlines()[0].replace("\r", " ").replace("%", "")
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"exit-code={code}\n")
        handle.write(f"result={result_name(code)}\n")
        handle.write(f"detail={first}\n")


def mask_skillgate_secrets() -> None:
    for _name, value in _secret_values():
        print(f"::add-mask::{value}", flush=True)


def redact(text: str) -> str:
    redacted = text
    for _name, value in _secret_values():
        redacted = redacted.replace(value, "***")
    return redacted


def _secret_values() -> list[tuple[str, str]]:
    return [
        (name, value)
        for name, value in os.environ.items()
        if value and _is_secret_name(name)
    ]


def _is_secret_name(name: str) -> bool:
    return name.startswith("SKILLGATE_") and any(marker in name for marker in _SECRET_MARKERS)


def _write(stream, text: str) -> None:
    if not text:
        return
    stream.write(text)
    if not text.endswith("\n"):
        stream.write("\n")
    stream.flush()


if __name__ == "__main__":
    sys.exit(main())
