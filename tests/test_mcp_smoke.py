"""Headless smoke test for the hosted Skill Gate MCP server.

Skipped unless SKILLGATE_TOKEN is set. CI stays green without the secret.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest

MCP_URL = "https://mcp.skill-gate-ai.app"
EXPECTED_TOOLS = frozenset({"check_skill", "run_eval", "gate"})

pytestmark = pytest.mark.skipif(
    not os.environ.get("SKILLGATE_TOKEN"),
    reason="SKILLGATE_TOKEN not set",
)


def _rpc_messages(response: httpx.Response) -> list[dict]:
    ctype = (response.headers.get("content-type") or "").split(";", 1)[0].strip()
    text = response.text
    if ctype == "text/event-stream" or text.lstrip().startswith("event:") or "\ndata:" in text:
        messages: list[dict] = []
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            messages.append(json.loads(payload))
        return messages
    body = response.json()
    return [body] if isinstance(body, dict) else list(body)


def test_hosted_mcp_lists_gate_tools() -> None:
    token = os.environ["SKILLGATE_TOKEN"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-03-26",
    }
    initialize = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "skillgate-oss-smoke", "version": "0.7.9"},
        },
    }
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        init = client.post(MCP_URL, headers=headers, json=initialize)
        init.raise_for_status()
        init_msg = _rpc_messages(init)[0]
        assert init_msg.get("result"), init_msg

        session = init.headers.get("mcp-session-id")
        if session:
            headers = {**headers, "mcp-session-id": session}

        client.post(
            MCP_URL,
            headers=headers,
            json={"jsonrpc": "2.0", "method": "notifications/initialized"},
        )
        listed = client.post(
            MCP_URL,
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        listed.raise_for_status()
        result = _rpc_messages(listed)[0]["result"]
        names = {tool["name"] for tool in result["tools"]}
    missing = EXPECTED_TOOLS - names
    assert not missing, f"missing tools {sorted(missing)}; got {sorted(names)}"
