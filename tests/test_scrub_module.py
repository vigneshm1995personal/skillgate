from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from skillgate_ai import api_payloads, scrub

ROOT = Path(__file__).resolve().parents[1]


def test_api_payloads_reexports_scrub() -> None:
    assert api_payloads.scrub_browser_payload is scrub.scrub_browser_payload
    assert api_payloads.scrub_config is scrub.scrub_config


def test_scrub_owner_module() -> None:
    assert scrub.scrub_browser_payload.__module__ == "skillgate_ai.scrub"


def test_domain_scrub_paths_do_not_load_api_payloads() -> None:
    script = """
import skillgate_ai.gate
import skillgate_ai.history
import skillgate_ai.compare.payload as compare_payload
from skillgate_ai.history import _scrub_history_row
from skillgate_ai.compare.payload import scrub_customer_compare_payload

_scrub_history_row({"report": {"judge": {"model": "x"}}})
scrub_customer_compare_payload({"arms": []})
import sys
if "skillgate_ai.api_payloads" in sys.modules:
    raise SystemExit(1)
"""
    proc = subprocess.run(
        [sys.executable, "-I", "-c", script],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout


def test_mcp_tools_still_imports_scrub() -> None:
    pytest.importorskip("mcp")
    from skillgate_ai.mcp import tools as mcp_tools

    assert mcp_tools.scrub_browser_payload is scrub.scrub_browser_payload
