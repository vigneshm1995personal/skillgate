"""Copy the built React UI into the Python package before sdist/wheel.

Editable checkouts serve ``web/dist`` directly. A published wheel must contain
``skillgate_ai/web_static`` so ``pip install skillgate-ai`` + ``skillgate ui``
works without pnpm.

The CLI Docker image copies ``src`` + ``pyproject.toml`` only — no ``web/`` —
so ``build_py`` must not require the UI there. ``sdist`` (PyPI) still requires it.

This module lives next to the package so setuptools cmdclass can import it
during an isolated ``python -m build``. It is not installed as a public
module (``packages.find`` only includes ``skillgate_ai*``).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

try:
    from setuptools.command.build_py import build_py as _build_py
    from setuptools.command.sdist import sdist as _sdist
except ImportError:  # pytest / runtime; cmdclass is unused
    _build_py = object
    _sdist = object

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
DEFAULT_DEST = SRC / "skillgate_ai" / "web_static"
DEFAULT_WEB_DIST = ROOT / "web" / "dist"
DEFAULT_WEB_DIR = ROOT / "web"
DEFAULT_EXAMPLES_DEST = SRC / "skillgate_ai" / "examples"
EXAMPLE_NAMES = ("pdf", "pdf-sabotaged")


def web_tree_present(web_dir: Path = DEFAULT_WEB_DIR) -> bool:
    return (web_dir / "package.json").is_file()


def bundle_web_static(
    *,
    dest: Path = DEFAULT_DEST,
    web_dist: Path = DEFAULT_WEB_DIST,
    web_dir: Path = DEFAULT_WEB_DIR,
    required: bool = False,
) -> Path | None:
    """Place ``index.html`` under ``dest``.

    When ``web/`` and pnpm are present, always rebuild so a leftover
    ``web_static`` cannot ship an older asset hash than ``pnpm build``.
    Docker copies ``src/`` only — then the committed ``web_static`` is used.
    """
    dest = dest.resolve()
    web_dist = web_dist.resolve()
    package_json = web_dir / "package.json"
    pnpm = shutil.which("pnpm")
    if package_json.is_file() and pnpm:
        subprocess.check_call([pnpm, "--dir", str(web_dir), "install", "--frozen-lockfile"])
        subprocess.check_call([pnpm, "--dir", str(web_dir), "build"])
    if (web_dist / "index.html").is_file():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(web_dist, dest)
        return dest
    if (dest / "index.html").is_file():
        return dest
    if required:
        raise SystemExit(
            "React UI is missing from the package. From the repo run:\n"
            "  cd web && pnpm install && pnpm build"
        )
    return None


def bundle_examples(*, dest: Path = DEFAULT_EXAMPLES_DEST) -> Path | None:
    dest = dest.resolve()
    copied = False
    for name in EXAMPLE_NAMES:
        src = ROOT / "skills" / name
        if not (src / "SKILL.md").is_file():
            continue
        target = dest / name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(
            src,
            target,
            ignore=shutil.ignore_patterns(".git", "__pycache__", ".skillgate", "*.jsonl"),
        )
        copied = True
    return dest if copied or dest.exists() else None


class build_py(_build_py):
    def run(self) -> None:
        editable = bool(getattr(self, "editable_mode", False))
        # Wheels/sdists rebuild from web/. Editable installs keep the
        # committed tree so CI can diff git vs a fresh `pnpm build`.
        # CLI Docker has no web/; it packages the committed folder.
        if not editable:
            bundle_web_static(required=web_tree_present())
        bundle_examples()
        super().run()


class sdist(_sdist):
    def run(self) -> None:
        bundle_web_static(required=True)
        bundle_examples()
        super().run()
