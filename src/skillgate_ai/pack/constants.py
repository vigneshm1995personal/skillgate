"""Read and write eval packs on disk."""

from __future__ import annotations

import re

FIXTURE_DIR = "evals/fixtures"
GOLDEN_DIR = "evals/goldens"
ASSET_DIR = "assets"
DEFAULT_FIXTURE_GLOB = f"{FIXTURE_DIR}/*"
CASE_SUFFIXES = {".md"}
_SKIP_DIR_NAMES = {".git", "__pycache__", ".skillgate", "node_modules"}
_SKIP_FILE_NAMES = {".ds_store", "thumbs.db"}
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
PDF_DEMO_FIXTURE_NAMES = frozenset(
    {"alpha.pdf", "beta.pdf", "hello.pdf", "invoice.pdf", "notes.pdf"}
)
# Underscore/hyphen count as separators so receipt_image.txt is a photo stand-in.
_UNSYNTHESIZABLE = re.compile(
    r"(?:^|[^a-z0-9])(photo|photos|image|images|png|jpe?g|screenshot|scan|scans)(?:[^a-z0-9]|$)",
    re.IGNORECASE,
)
_PDF_MAGIC = b"%PDF"
_IMAGE_MAGICS = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
)


TEXT_SUFFIXES = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".csv",
    ".py",
    ".js",
    ".ts",
    ".toml",
    ".xml",
    ".html",
    ".css",
    ".sh",
    ".svg",
}
PREVIEW_TEXT_LIMIT = 80_000
