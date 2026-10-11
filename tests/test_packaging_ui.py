from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_build() -> object:
    spec = importlib.util.spec_from_file_location(
        "skillgate_build", ROOT / "src" / "skillgate_build.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pyproject_packages_web_static() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "web_static/*" in text
    assert "skillgate_build.build_py" in text
    assert "skillgate_build.sdist" in text


def test_bundle_copies_built_dist(tmp_path: Path) -> None:
    module = _load_build()
    dist = tmp_path / "dist"
    dest = tmp_path / "web_static"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html><title>Skill Gate</title></html>\n", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log('ok')\n", encoding="utf-8")
    out = module.bundle_web_static(
        dest=dest,
        web_dist=dist,
        web_dir=tmp_path / "missing-web",
        required=True,
    )
    assert out == dest.resolve()
    assert (dest / "index.html").is_file()
    assert "Skill Gate" in (dest / "index.html").read_text(encoding="utf-8")
    assert (dest / "assets" / "app.js").is_file()
