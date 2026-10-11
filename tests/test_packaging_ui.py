from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGED_UI = ROOT / "src" / "skillgate_ai" / "web_static"
WEB_DIR = ROOT / "web"


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


def test_bundle_is_optional_without_web(tmp_path: Path) -> None:
    module = _load_build()
    out = module.bundle_web_static(
        dest=tmp_path / "web_static",
        web_dist=tmp_path / "dist",
        web_dir=tmp_path / "missing-web",
        required=False,
    )
    assert out is None
    assert module.web_tree_present(tmp_path / "missing-web") is False


GIT_UI_PREFIX = "src/skillgate_ai/web_static/"


def _tree_bytes(root: Path) -> dict[str, bytes]:
    files: dict[str, bytes] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files[path.relative_to(root).as_posix()] = path.read_bytes()
    return files


def _git_indexed_web_static() -> dict[str, bytes]:
    """Bytes git would commit/checkout — not a working tree `pip install -e` just rebuilt."""
    raw = subprocess.check_output(
        ["git", "ls-files", "-z", GIT_UI_PREFIX],
        cwd=ROOT,
    )
    files: dict[str, bytes] = {}
    for rel in filter(None, raw.decode().split("\0")):
        key = rel[len(GIT_UI_PREFIX) :] if rel.startswith(GIT_UI_PREFIX) else rel
        files[key] = subprocess.check_output(["git", "show", f":{rel}"], cwd=ROOT)
    return files


def test_web_static_is_tracked_and_not_gitignored() -> None:
    """The wheel copies this folder; it must be in git, not a leftover local build."""
    tracked = subprocess.check_output(
        ["git", "ls-files", "src/skillgate_ai/web_static/index.html"],
        cwd=ROOT,
        text=True,
    ).strip()
    assert tracked == "src/skillgate_ai/web_static/index.html"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "src/skillgate_ai/web_static/index.html"],
        cwd=ROOT,
        check=False,
    )
    assert ignored.returncode == 1, "src/skillgate_ai/web_static/ is gitignored"


def test_web_static_matches_fresh_pnpm_build(tmp_path: Path) -> None:
    """Fail when git's web_static is an older Vite bundle than `pnpm build` of web/.

    Reads the git index, not the working tree, so `pip install -e` rebuilding
    src/skillgate_ai/web_static cannot hide a stale commit.
    """
    git_tree = _git_indexed_web_static()
    assert "index.html" in git_tree, (
        "src/skillgate_ai/web_static/index.html is not in git. From the repo:\n"
        "  cd web && pnpm install && pnpm build\n"
        "  python3 -c 'from skillgate_build import bundle_web_static; bundle_web_static()'\n"
        "  git add src/skillgate_ai/web_static"
    )
    working = PACKAGED_UI / "index.html"
    original = working.read_bytes() if working.is_file() else None
    working.parent.mkdir(parents=True, exist_ok=True)
    working.write_text("POISON — pip install -e rebuilt the working tree\n", encoding="utf-8")
    try:
        pnpm = shutil.which("pnpm")
        assert pnpm, "pnpm is required to verify the packaged UI against a fresh web/ build"
        fresh = tmp_path / "dist"
        subprocess.check_call([pnpm, "--dir", str(WEB_DIR), "exec", "tsc", "-b"], cwd=WEB_DIR)
        subprocess.check_call(
            [
                pnpm,
                "--dir",
                str(WEB_DIR),
                "exec",
                "vite",
                "build",
                "--outDir",
                str(fresh),
                "--emptyOutDir",
            ],
            cwd=WEB_DIR,
        )
        fresh_tree = _tree_bytes(fresh)
        assert git_tree.keys() == fresh_tree.keys(), (
            "src/skillgate_ai/web_static file list is stale vs a fresh `pnpm build` of web/.\n"
            f"only in git:   {sorted(git_tree.keys() - fresh_tree.keys())}\n"
            f"only in fresh: {sorted(fresh_tree.keys() - git_tree.keys())}\n"
            "Rebuild and commit web_static."
        )
        mismatched = sorted(name for name, data in git_tree.items() if data != fresh_tree[name])
        assert not mismatched, (
            "src/skillgate_ai/web_static is stale vs a fresh `pnpm build` of web/.\n"
            f"differ: {mismatched}\n"
            "Rebuild and commit web_static."
        )
    finally:
        if original is not None:
            working.write_bytes(original)
        elif working.is_file():
            working.unlink()


def test_bundle_overwrites_stale_dest_from_dist(tmp_path: Path) -> None:
    module = _load_build()
    dist = tmp_path / "dist"
    dest = tmp_path / "web_static"
    (dest / "assets").mkdir(parents=True)
    (dest / "index.html").write_text(
        '<script src="/assets/index-OLDHASH.js"></script>\n', encoding="utf-8"
    )
    (dest / "assets" / "index-OLDHASH.js").write_text("old\n", encoding="utf-8")
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text(
        '<script src="/assets/index-NEWHASH.js"></script>\n', encoding="utf-8"
    )
    (dist / "assets" / "index-NEWHASH.js").write_text("new\n", encoding="utf-8")
    module.bundle_web_static(
        dest=dest,
        web_dist=dist,
        web_dir=tmp_path / "missing-web",
        required=True,
    )
    html = (dest / "index.html").read_text(encoding="utf-8")
    assert "index-NEWHASH.js" in html
    assert not (dest / "assets" / "index-OLDHASH.js").is_file()
    assert (dest / "assets" / "index-NEWHASH.js").is_file()
