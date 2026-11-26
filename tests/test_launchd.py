from __future__ import annotations

import plistlib
from pathlib import Path

import pytest

from skillgate_ai.helper import install_launchd_plist as helper_install_launchd_plist
from skillgate_ai.launchd import write_launch_agent
from skillgate_ai.sync import install_launchd_plist as sync_install_launchd_plist

LABEL = "com.example.skillgate.test"


@pytest.fixture
def launch_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr("skillgate_ai.launchd.shutil.which", lambda _: "/opt/bin/skillgate")
    return tmp_path


def test_write_launch_agent_omits_keep_alive_by_default(launch_home: Path) -> None:
    launch_dir = launch_home / "LaunchAgents"
    dest = write_launch_agent(
        launch_dir, label=LABEL, program_arguments=["/opt/bin/skillgate", "helper"]
    )
    plist = plistlib.loads(dest.read_bytes())
    assert "KeepAlive" not in plist
    assert (dest.stat().st_mode & 0o777) == 0o600
    assert (launch_dir.stat().st_mode & 0o777) == 0o755


def test_write_launch_agent_writes_keep_alive_false(launch_home: Path) -> None:
    launch_dir = launch_home / "LaunchAgents"
    dest = write_launch_agent(
        launch_dir,
        label=LABEL,
        program_arguments=["/opt/bin/skillgate", "helper"],
        keep_alive=False,
    )
    assert plistlib.loads(dest.read_bytes())["KeepAlive"] is False


def test_helper_plist_bytes_unchanged(launch_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.helper.sys.platform", "darwin")
    expected = plistlib.dumps(
        {
            "Label": "com.skillgate-ai.helper",
            "RunAtLoad": True,
            "KeepAlive": False,
            "ProgramArguments": ["/opt/bin/skillgate", "helper"],
        }
    )
    assert helper_install_launchd_plist().read_bytes() == expected


def test_sync_plist_bytes_unchanged(launch_home: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("skillgate_ai.sync.sys.platform", "darwin")
    expected = plistlib.dumps(
        {
            "Label": "com.skillgate-ai.sync",
            "RunAtLoad": True,
            "ProgramArguments": [
                "/opt/bin/skillgate",
                "sync",
                "--repo",
                "https://github.com/acme/skills.git",
                "--targets",
                "cursor",
                "--interval",
                "60",
            ],
        }
    )
    assert (
        sync_install_launchd_plist(
            "https://github.com/acme/skills.git", targets=["cursor"], interval=60
        ).read_bytes()
        == expected
    )
