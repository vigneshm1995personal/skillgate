"""Pack file sniffing and golden-path helpers. No YAML models."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from skillgate_ai.pack import GOLDEN_DIR

GOLDEN_TAIL_CHARS = 8000
_OUTPUT_MAGICS = (
    (b"\xff\xd8\xff", "jpeg", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"%PDF", "pdf", "application/pdf"),
    (b"GIF87a", "gif", "image/gif"),
    (b"GIF89a", "gif", "image/gif"),
)
_BINARY_GOLDEN = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp"}


def sniff_output_bytes(data: bytes) -> dict[str, Any]:
    """Classify produced bytes: text vs image/pdf/NUL. Never invents a body."""
    size = len(data)
    for magic, name, mime in _OUTPUT_MAGICS:
        if data.startswith(magic):
            return {"kind": "bytes", "magic": name, "mime": mime, "size": size}
    if b"\0" in data[:1024]:
        return {"kind": "bytes", "magic": "nul", "mime": None, "size": size}
    return {"kind": "text", "magic": None, "mime": None, "size": size}


def read_capped_text(path: str | Path | None, *, limit: int = GOLDEN_TAIL_CHARS) -> str | None:
    if path is None:
        return None
    file_path = Path(path)
    if not file_path.is_file():
        return None
    data = file_path.read_bytes()
    if b"\0" in data[:1024]:
        return None
    text = data.decode("utf-8", errors="replace")
    if limit <= 0:
        return ""
    return text[-limit:]


def golden_kind(path: str | Path) -> Literal["json", "text", "bytes"]:
    suffix = Path(path).suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in _BINARY_GOLDEN:
        return "bytes"
    return "text"


def file_inside_skill(root: Path, path: Path) -> Path | None:
    try:
        resolved = path.expanduser().resolve()
        resolved.relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def resolve_golden_src(root: Path, case_id: str, golden_path: str | None) -> Path | None:
    root = root.resolve()
    folder = root / GOLDEN_DIR
    if golden_path:
        rel = golden_path.replace("\\", "/").lstrip("/")
        parts = Path(rel).parts
        if ".." not in parts:
            packed = file_inside_skill(root, root / rel)
            if packed is not None:
                return packed
        named = file_inside_skill(root, folder / Path(rel).name)
        if named is not None:
            return named
    if folder.is_dir():
        matches = sorted(
            path
            for path in folder.iterdir()
            if path.is_file() and path.stem == case_id
        )
        if matches:
            return matches[0]
    return None
