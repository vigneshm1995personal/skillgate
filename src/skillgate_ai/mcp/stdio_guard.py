"""Own fd 0/1 for the MCP protocol; point the real fd 0/1 at devnull/stderr."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True)
class ProtocolStreams:
    stdin: TextIO
    stdout: TextIO


def install() -> ProtocolStreams:
    if os.environ.get("SKILLGATE_MCP_NO_STDIO_GUARD") == "1":
        return ProtocolStreams(stdin=sys.stdin, stdout=sys.stdout)

    sys.stdout.flush()
    proto_in = os.dup(0)
    proto_out = os.dup(1)
    devnull_fd = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull_fd, 0)
    os.close(devnull_fd)
    os.dup2(2, 1)
    sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115
    sys.stdout = sys.stderr
    return ProtocolStreams(
        stdin=open(proto_in, encoding="utf-8", errors="replace", closefd=True),
        stdout=open(
            proto_out, mode="w", encoding="utf-8", errors="replace", closefd=True, buffering=1
        ),
    )
