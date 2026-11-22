"""Per-user macOS LaunchAgent plists for `skillgate helper` and `skillgate sync`."""

from __future__ import annotations

import os
import plistlib
import shutil
from pathlib import Path


def launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def skillgate_binary() -> str:
    return shutil.which("skillgate") or "skillgate"


def write_launch_agent(
    launch_dir: Path,
    *,
    label: str,
    program_arguments: list[str],
    keep_alive: bool | None = None,
) -> Path:
    """Write ``<launch_dir>/<label>.plist`` (0644) with RunAtLoad; dir is 0755."""
    plist: dict[str, object] = {
        "Label": label,
        "RunAtLoad": True,
        "ProgramArguments": program_arguments,
    }
    if keep_alive is not None:
        plist["KeepAlive"] = keep_alive
    launch_dir.mkdir(parents=True, exist_ok=True)
    try:  # noqa: SIM105
        os.chmod(launch_dir, 0o755)
    except OSError:
        pass
    dest = launch_dir / f"{label}.plist"
    with open(dest, "wb") as handle:
        plistlib.dump(plist, handle)
    os.chmod(dest, 0o644)
    return dest
