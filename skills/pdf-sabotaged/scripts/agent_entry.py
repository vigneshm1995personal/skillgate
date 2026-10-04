#!/usr/bin/env python3
"""Route SKILLGATE_TASK to bundled PDF scripts. Used by the demo harness and as a Cursor Agent hint."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORK = Path.cwd()


def _out(prompt: str, default: str) -> str:
    match = re.search(r"(output/[A-Za-z0-9_.-]+)", prompt)
    return match.group(1) if match else default


def _pdfs() -> list[Path]:
    return sorted(p for p in WORK.glob("*.pdf") if p.is_file())


def _run(script: str, args: list[str]) -> int:
    cmd = [sys.executable, str(HERE / script), *args]
    proc = subprocess.run(cmd, cwd=str(WORK), check=False)
    return proc.returncode


def main() -> int:
    prompt = os.environ.get("SKILLGATE_TASK", "")
    lower = prompt.lower()
    Path("output").mkdir(exist_ok=True)
    pdfs = _pdfs()

    if any(w in lower for w in ("merge", "combine", "deck")):
        dest = _out(prompt, "output/merged.pdf")
        names = re.findall(r"([A-Za-z0-9_.-]+\.pdf)", prompt)
        inputs = [WORK / n for n in names if (WORK / n).exists() and n not in {Path(dest).name}]
        if len(inputs) < 2:
            inputs = pdfs[:2]
        if len(inputs) < 2:
            print("need two PDFs to merge", file=sys.stderr)
            return 1
        return _run("merge_pdfs.py", [dest, *[str(p) for p in inputs]])

    if "rotate" in lower:
        dest = _out(prompt, "output/rotated.pdf")
        source = pdfs[0] if pdfs else WORK / "hello.pdf"
        degrees = "90"
        match = re.search(r"(\d+)\s*degrees", lower)
        if match:
            degrees = match.group(1)
        return _run("rotate_pdf.py", [str(source), dest, "--degrees", degrees])

    if any(w in lower for w in ("create", "titled", "produce a pdf", "new pdf")):
        dest = _out(prompt, "output/status.pdf")
        title = "Untitled"
        body = ""
        titled = re.search(r"titled\s+([^\"']+?)(?:\s+that|\s+containing|\s+with|\s*$)", prompt, re.I)
        if titled:
            title = titled.group(1).strip(" .")
        quoted = re.findall(r'"([^"]+)"', prompt)
        if quoted:
            body = quoted[-1]
        elif "contains the sentence" in lower:
            after = re.search(r"sentence\s+(.+)$", prompt, re.I)
            if after:
                body = after.group(1).strip(" .")
        return _run("create_pdf.py", [dest, "--title", title, "--body", body])

    if any(w in lower for w in ("extract", "dump", "text")):
        dest = _out(prompt, "output/extracted.txt")
        names = re.findall(r"([A-Za-z0-9_.-]+\.pdf)", prompt)
        source = WORK / names[0] if names else (pdfs[0] if pdfs else WORK / "hello.pdf")
        return _run("extract_text.py", [str(source), dest])

    print("unrecognized PDF task", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
