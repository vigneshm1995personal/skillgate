"""Copy the built React UI into the Python package before sdist/wheel.

Editable checkouts serve ``web/dist`` directly. A published wheel must contain
``skillgate_ai/web_static`` so ``pip install skillgate-ai`` + ``skillgate ui``
works without pnpm.

This module lives next to the package so setuptools cmdclass can import it
during an isolated ``python -m build``. It is not installed as a public
module (``packages.find`` only includes ``skillgate_ai*``).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from setuptools.command.build_py import build_py as _build_py
from setuptools.command.sdist import sdist as _sdist

SRC = Path(__file__).resolve().parent
ROOT = SRC.parent
DEFAULT_DEST = SRC / "skillgate_ai" / "web_static"
DEFAULT_WEB_DIST = ROOT / "web" / "dist"
DEFAULT_WEB_DIR = ROOT / "web"


def bundle_web_static(
    *,
    dest: Path = DEFAULT_DEST,
    web_dist: Path = DEFAULT_WEB_DIST,
    web_dir: Path = DEFAULT_WEB_DIR,
    required: bool = False,
) -> Path | None:
    """Place ``index.html`` under ``dest``. Build with pnpm when ``web/dist`` is missing."""
    dest = dest.resolve()
    web_dist = web_dist.resolve()
    if (dest / "index.html").is_file() and not (web_dist / "index.html").is_file():
        return dest
    if not (web_dist / "index.html").is_file():
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


class build_py(_build_py):
    def run(self) -> None:
        required = not getattr(self, "editable_mode", False)
        bundle_web_static(required=required)
        super().run()


class sdist(_sdist):
    def run(self) -> None:
        bundle_web_static(required=True)
        super().run()
