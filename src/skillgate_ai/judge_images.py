"""Inline JPEG/PNG data URLs for scoring. Never logs bytes."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Mapping

from skillgate_ai.pack_files import sniff_output_bytes

IMAGE_MAX_BYTES = 4 * 1024 * 1024
IMAGE_MAX_COUNT = 3
INLINE_MAGICS = {"jpeg": "image/jpeg", "png": "image/png"}


def _resolved_under(path: Path, root: Path) -> Path | None:
    """Return path if it resolves inside root. Blocks `..` and absolute escapes."""
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return None
    return resolved


def collect_images(
    *,
    artifacts: list[dict[str, Any]],
    golden: Mapping[str, Any] | None,
    actual: Mapping[str, Any] | None,
    workspace: Path | None,
    skill_root: Path | None,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """JPEG/PNG data URLs only. Caps: 4 MiB each, 3 images. Never logs bytes."""
    candidates: list[tuple[Path, str]] = []
    seen: set[Path] = set()

    def consider(path: Path, label: str, root: Path | None) -> None:
        if root is None:
            return
        resolved = _resolved_under(path, root)
        if resolved is None or resolved in seen or not resolved.is_file():
            return
        seen.add(resolved)
        candidates.append((resolved, label))

    if workspace is not None:
        for row in artifacts:
            if not isinstance(row, Mapping) or not row.get("present"):
                continue
            magic = str(row.get("magic") or "")
            if magic not in INLINE_MAGICS:
                continue
            rel = str(row.get("path") or "").strip()
            if rel:
                consider(workspace / rel, rel, workspace)
        if actual and actual.get("present") and str(actual.get("magic") or "") in INLINE_MAGICS:
            rel = str(actual.get("path") or "").strip()
            if rel:
                consider(workspace / rel, rel, workspace)
    if golden and skill_root is not None:
        rel = str(golden.get("path") or "").strip()
        magic = str(golden.get("magic") or "")
        if rel and (not magic or magic in INLINE_MAGICS):
            consider(skill_root / rel, rel, skill_root)

    images: list[dict[str, str]] = []
    omitted: list[dict[str, Any]] = []
    for path, label in candidates:
        try:
            size = path.stat().st_size
        except OSError:
            omitted.append({"path": label, "reason": "unreadable"})
            continue
        if size > IMAGE_MAX_BYTES:
            omitted.append({"path": label, "size": size, "reason": "too large"})
            continue
        if len(images) >= IMAGE_MAX_COUNT:
            omitted.append({"path": label, "size": size, "reason": "over cap"})
            continue
        try:
            with path.open("rb") as handle:
                header = handle.read(16)
                magic = sniff_output_bytes(header).get("magic")
                if magic not in INLINE_MAGICS:
                    continue
                data = header + handle.read()
        except OSError:
            omitted.append({"path": label, "reason": "unreadable"})
            continue
        if len(data) > IMAGE_MAX_BYTES:
            omitted.append({"path": label, "size": len(data), "reason": "too large"})
            continue
        b64 = base64.b64encode(data).decode("ascii")
        images.append(
            {
                "type": "input_image",
                "image_url": f"data:{INLINE_MAGICS[magic]};base64,{b64}",
            }
        )
    return images, omitted
