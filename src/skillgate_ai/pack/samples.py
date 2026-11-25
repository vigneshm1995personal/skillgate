"""Read and write eval packs on disk."""

from __future__ import annotations

from pathlib import Path

from skillgate_ai.demo_files import write_pdf
from skillgate_ai.pack.constants import (
    _IMAGE_MAGICS,
    _PDF_MAGIC,
    _UNSYNTHESIZABLE,
    IMAGE_SUFFIXES,
)
from skillgate_ai.pack.pathsafe import implied_fixture_name


class CannotSynthesizeFixture(ValueError):
    """Photo/scan samples cannot be faked; the check needs a real upload."""

    def __init__(self, message: str | None = None):
        super().__init__(
            message
            or "This check needs a real photo or scan — upload one instead of a generated sample."
        )


def implies_photo_scan(*parts: object) -> bool:
    """True when skill/check/path/content is a photo, scan, or image input."""
    blob = " ".join(str(part or "") for part in parts)
    return bool(_UNSYNTHESIZABLE.search(blob))


def as_fixture_bytes(content: str | bytes) -> bytes:
    return content.encode("utf-8") if isinstance(content, str) else bytes(content)


def is_authentic_fixture_bytes(dest: str, content: str | bytes) -> bool:
    """Reject ASCII stand-ins for PDF/image binaries (e.g. 33-byte fake .pdf)."""
    suffix = Path(dest).suffix.lower()
    data = as_fixture_bytes(content)
    if suffix == ".pdf":
        return data.startswith(_PDF_MAGIC) and len(data) >= 100
    if suffix in IMAGE_SUFFIXES:
        if len(data) < 200:
            return False
        if any(data.startswith(magic) for magic in _IMAGE_MAGICS):
            return True
        return data[8:12] == b"WEBP" if data.startswith(b"RIFF") else False
    return True


def cannot_synthesize_sample(*, dest: str = "", prompt: str = "", description: str = "") -> bool:
    """True for photo/scan inputs we must not fake as a placeholder image."""
    if implies_photo_scan(prompt, description, dest):
        return True
    name = dest or implied_fixture_name(f"{prompt} {description}")
    return Path(name).suffix.lower() in IMAGE_SUFFIXES


def generate_sample_bytes(*, dest: str, prompt: str = "") -> bytes:
    """Generic sample from dest extension + prompt words. No skill-name switch."""
    name = Path(dest).name or "sample.txt"
    suffix = Path(name).suffix.lower()
    stem = Path(name).stem.replace("-", " ") or "sample"
    hint = " ".join((prompt or stem).split())[:180] or "alpha / beta / gamma"
    if suffix in IMAGE_SUFFIXES or cannot_synthesize_sample(dest=dest, prompt=prompt):
        raise CannotSynthesizeFixture()
    if suffix == ".pdf":
        from tempfile import NamedTemporaryFile

        with NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
            path = Path(tmp.name)
            write_pdf(path, f"Sample input: {hint[:80]}")
            return path.read_bytes()
    if suffix == ".json":
        body = f'{{\n  "source": {stem!r},\n  "note": {hint!r},\n  "total": "12.40"\n}}\n'
        return body.encode("utf-8")
    if suffix == ".csv":
        return f"item,amount\n{stem},12.40\nnote,{hint}\n".encode()
    text = f"Sample input for this check.\nItem: {stem}\nNote: {hint}\nTotal: 12.40\n"
    return text.encode("utf-8")
