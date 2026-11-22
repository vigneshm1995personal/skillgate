# PR #3 — Dependencies & CI hardening (lockfile, SHA pins, Python matrix, gated release)

## 1. Scope

This PR changes only CI and dependency plumbing. Runtime behavior in `src/` does not change.

| In scope | Out of scope (see §11) |
|---|---|
| Commit `uv.lock`. CI installs from it in frozen/locked mode. | Any `src/` change |
| Pin every third-party action to a full commit SHA, with a version comment on the same line | Security and retry fixes (#75), typing (#76) |
| Python matrix 3.11 / 3.12 / 3.13 for the `test` and `integration` jobs | Test fixes, dead-code removal |
| Gate `release.yml` (build, pypi, ghcr) on a green gate run for the same ref/tag | Loosening any check, or removing any CI job |
| `gate.yml`: `permissions`, `concurrency`, uv/pnpm/pip caches | Major-version bumps of actions (Dependabot handles these later) |
| `.github/dependabot.yml` | |
| Dockerfile installs dependencies from `uv.lock` | |

---

## 2. Files to create or modify

| Path | Action | Summary |
|---|---|---|
| `uv.lock` | **create (commit)** | Regenerate with `uv lock`, then commit. The file already exists locally but is untracked. |
| `.gitignore` | modify | Delete line 31 (`uv.lock`). |
| `.github/workflows/gate.yml` | modify | SHA pins, `permissions`, `concurrency`, `workflow_call` + `ref` input, uv install, matrix, caches |
| `.github/workflows/release.yml` | modify | SHA pins, call `gate.yml`, `needs:` chain, `uv build`, concurrency |
| `.github/workflows/skillgate-action.yml` | modify | SHA pin for `actions/checkout` |
| `action.yml` | modify | SHA pin for `actions/setup-python`. This composite action runs inside `skillgate-action.yml`. |
| `.github/dependabot.yml` | **create** | Ecosystems: uv, npm (`/web`), github-actions, docker |
| `Dockerfile` | modify | Install dependencies from `uv.lock` with `uv sync --locked`; pinned uv image stage |
| `pyproject.toml` | modify | Add classifier `Programming Language :: Python :: 3.13`. Do not change `requires-python`, ruff, or mypy targets. |
| `CONTRIBUTING.md` | modify | Add a short "Dependencies / lockfile" section: `uv sync --locked --extra dev`; run `uv lock` after editing deps |
| `CHANGELOG.md` | modify | Add an `Unreleased → CI` entry |

No other files change.

---

## 3. Action pin table (every `uses:` across all workflows plus `action.yml`)

Line format: `uses: owner/repo@<40-char-sha> # vX.Y.Z`. Dependabot reads and updates the trailing comment.

> **These SHAs were not verified against the GitHub API when this spec was written.** They are the published commit SHAs for the stated releases, as known at writing time. Before committing, the implementer must:
> 1. Pick the **newest release within the current major** (v4, v5, v3, v1).
> 2. Resolve it with `gh api repos/<owner>/<repo>/commits/<tag> --jq .sha`. This returns the commit SHA and dereferences annotated tags.
> 3. If a newer patch exists than the one listed below, use the newer one and update the comment to match.

| # | Action | Used in (file → job/step) | Current ref | Pin to (release) | Full SHA |
|---|---|---|---|---|---|
| 1 | `actions/checkout` | gate.yml: all 7 jobs; release.yml: build, ghcr; skillgate-action.yml: action | `@v4` | `v4.2.2` (or newest v4.x) | `11bd71901bbe5b1630ceea73d27597364c9af683` |
| 2 | `actions/setup-python` | gate.yml: lint, test, integration, gate, web-build, oss-surface; release.yml: build; **action.yml** | `@v5` | `v5.6.0` (or newest v5.x) | `a26af69be951a213d495a4c3e4e4022e16d87065` |
| 3 | `pnpm/action-setup` | gate.yml: test, web-build; release.yml: build | `@v4` | `v4.1.0` (or newest v4.x) | `a7487c7e89a18df4991f7f222e4898a00d66ddda` (verify at implement time) |
| 4 | `actions/setup-node` | gate.yml: test, web-build; release.yml: build | `@v4` | `v4.4.0` (or newest v4.x) | `49933ea5288caeca8642d1e84afbd3f7d6820020` |
| 5 | `actions/upload-artifact` | release.yml: build | `@v4` | `v4.6.2` (or newest v4.x) | `ea165f8d65b6e75b540449e92b4886f43607fa02` |
| 6 | `actions/download-artifact` | release.yml: pypi | `@v4` | `v4.3.0` (or newest v4.x) | `d3f86a106a0bac45b974a628896c90dbdf5c8093` (verify at implement time) |
| 7 | `docker/login-action` | release.yml: ghcr | `@v3` | `v3.4.0` (or newest v3.x) | `74a5d142397b4f367a81961eba4e8cd7edddf772` (verify at implement time) |
| 8 | `pypa/gh-action-pypi-publish` | release.yml: pypi | `@release/v1` (**branch**) | `v1.12.4` (or newest v1.x **tag**) | `76f52bc884231f62b9a034ebfe128415bbaabdfe` |
| 9 | `astral-sh/setup-uv` (**new**) | gate.yml: lint, test, integration, gate, web-build, oss-surface; release.yml: build | — | newest v6.x (or current major) tag | **resolve at implement time**: `gh api repos/astral-sh/setup-uv/commits/<tag> --jq .sha` |
| — | `./` (local composite) | skillgate-action.yml | `./` | not pinned (local path) | n/a |

Docker images (not actions, pinned the same way):

| Image | Where | Pin |
|---|---|---|
| `python:3.12-slim-bookworm` | Dockerfile `PYTHON_IMAGE` | Already pinned by digest. Unchanged. |
| `ghcr.io/astral-sh/uv` (**new**) | Dockerfile `UV_IMAGE` | `ghcr.io/astral-sh/uv:<X.Y.Z>@sha256:<digest>`. Use the same uv version as `setup-uv`'s `version:` input. Resolve with `docker buildx imagetools inspect ghcr.io/astral-sh/uv:<X.Y.Z>` (index digest). |

**uv version pin:** pick one exact uv version (`X.Y.Z`, the version used to run `uv lock`). Use it in three places:
- `setup-uv` `with: version: "X.Y.Z"` in every job that uses it
- the Dockerfile `UV_IMAGE` tag
- `CONTRIBUTING.md`

---

## 4. Python matrix

`pyproject.toml`: `requires-python = ">=3.11"` stays. Add the `3.13` classifier. `tool.ruff.target-version = "py311"` and `tool.mypy.python_version = "3.11"` stay as they are.

| Job | Python | Rationale |
|---|---|---|
| `lint` | `3.12` only | ruff and mypy already target 3.11 through config. The interpreter version doesn't change results. |
| `test` | **matrix `["3.11", "3.12", "3.13"]`**, `fail-fast: false` | Main runtime coverage for the supported range |
| `integration` | **matrix `["3.11", "3.12", "3.13"]`**, `fail-fast: false` | CLI-to-gate E2E. Cheap (no network); exercises version-sensitive stdlib paths. |
| `gate` | `3.12` only | Install-surface smoke; not version-sensitive |
| `web-build` | `3.12` only | Wheel is pure-Python (`py3-none-any`) |
| `oss-surface` | `3.12` only | Static repo-surface assertions |
| `docker` | none (image pins 3.12) | Unchanged |
| `release.yml` build | `3.12` only | Same as `web-build` |

To avoid running the same web work three times in `test`, the `pnpm/action-setup`, `setup-node` and "Web unit tests" steps get `if: matrix.python-version == '3.12'`. The web suite then runs once.

Job display names become `test (3.11)`, `test (3.12)`, `test (3.13)`, `integration (3.11)`, and so on. This follows from `name: test (${{ matrix.python-version }})`.

> **Branch protection:** after this merges, replace the required checks `test` and `integration` with the six matrix names. Otherwise PRs will block on checks that no longer report.

---

## 5. uv.lock and install commands

### 5.1 Lockfile

1. Delete `.gitignore` line 31 (`uv.lock`).
2. Regenerate from scratch with the pinned uv: `rm uv.lock && uv lock`. The lock is universal: one file covers 3.11 through 3.13 via resolution markers.
3. Check it locally: `uv sync --locked --extra dev && pytest -q -m "not integration"`.
4. Commit `uv.lock`.

### 5.2 CI install contract

**Workflow-level env** in `gate.yml`. Also set it on the `build` job in `release.yml`.

```yaml
env:
  UV_PYTHON_DOWNLOADS: never      # use the setup-python interpreter; never fetch one
  UV_LINK_MODE: copy
```

**Standard install step** for `lint`, `test`, `integration` and `oss-surface`. This replaces `pip install -e ".[dev]"`.

```yaml
- run: uv sync --locked --extra dev --python "${{ matrix.python-version || '3.12' }}"
- run: echo "$PWD/.venv/bin" >> "$GITHUB_PATH"
```

- `--locked` behaves like `--frozen` (it installs exactly what `uv.lock` says) and also **fails if `uv.lock` is out of date with `pyproject.toml`**. This is the drift check. Use `--locked` everywhere; do not use `--frozen`.
- `--extra dev` pulls `all`, which pulls `ui` and `docs`. This matches today's `.[dev]`. Do not use `--all-extras`: `dev` already covers everything, and spelling it out keeps parity with the pip path in `CONTRIBUTING.md`.
- uv installs the project in editable mode by default, matching `pip install -e`.
- Adding `.venv/bin` to `GITHUB_PATH` means later steps (`ruff check`, `mypy src`, `pytest …`, `skillgate …`) **run unchanged**.

**`gate` job (core install only).** This replaces `pip install -e .`:

```yaml
- run: uv sync --locked --python 3.12          # no extras → core deps only
- run: echo "$PWD/.venv/bin" >> "$GITHUB_PATH"
```

uv virtualenvs do not ship `pip`, so the "core install pulls no ui/docs extras" script must stop calling `python -m pip freeze`. Replace only the freeze line with stdlib metadata. The names tuple and the failure condition stay the same, so the check is no weaker:

```python
from importlib.metadata import distributions

installed = {(d.metadata["Name"] or "").lower() for d in distributions()}
```

Remove the `subprocess` and `out` lines.

**`web-build` job and `release.yml` `build` job.** Replace `python -m pip install -U pip build` and `python -m build` with:

```yaml
- run: uv build            # PEP 517 build via setuptools + skillgate_build cmdclass (runs pnpm), isolated env
- run: python tests/assert_wheel_ui.py
```

The wheel-install smoke in `web-build` (`/tmp/wheelenv … pip install dist/*.whl[ui]`) **stays on unlocked pip on purpose**. It is the end-user install canary and catches upstream breakage that real `pip install skillgate-ai[ui]` users would hit. Add a one-line comment saying so.

### 5.3 Dockerfile

Install dependencies from the lockfile. Do not parse `pyproject.toml` with tomllib and pip-install unpinned.

```dockerfile
# syntax=docker/dockerfile:1

ARG PYTHON_IMAGE=python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
# uv X.Y.Z index digest — keep in sync with setup-uv `version:` in CI.
ARG UV_IMAGE=ghcr.io/astral-sh/uv:X.Y.Z@sha256:<digest>

FROM ${UV_IMAGE} AS uv

# --- Build stage ---
FROM ${PYTHON_IMAGE} AS build
WORKDIR /src
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=0 \
    PATH="/opt/venv/bin:$PATH"

# Locked core deps + docs extra (no ui: this image is the check CLI); cached when only src changes.
RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-editable --extra docs

COPY src ./src
COPY skills ./skills
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --extra docs
```

The `dev` and `runtime` stages stay **unchanged**. They still copy `/opt/venv` with `--chown=1001:1001` and keep the `USER appuser`, `ENTRYPOINT` and `CMD`. The `uv` binary lives only in the build stage and is not copied into runtime.

Constraints from `tests/test_dockerfile.py`, all still satisfied:
- First line is `# syntax=docker/dockerfile:1`.
- The text contains `python:3.12-slim-bookworm@sha256:`.
- It contains no `pnpm`, `serve` or `EXPOSE`.
- It keeps `COPY skills`.

`.dockerignore` does not exclude `uv.lock`, so it needs no change.

---

## 6. Release gating (`release.yml`)

**Approach: make `gate.yml` reusable (`workflow_call`) and call it from `release.yml`.** Every publish job then depends on a gate run against the *exact tag being released*.

Why not the alternatives:
- `workflow_run` can't key on a tag ref or on a `workflow_dispatch` input.
- A bare `needs:` can't cross workflows.

### 6.1 `gate.yml` trigger change

```yaml
on:
  push:
  pull_request:
  workflow_call:
    inputs:
      ref:
        description: "Git ref to check out (tag for releases). Empty = event ref."
        type: string
        required: false
        default: ""
```

Every `actions/checkout` step in `gate.yml` gets:

```yaml
with:
  ref: ${{ inputs.ref }}
```

Under `push` and `pull_request`, `inputs.ref` is empty, so checkout falls back to the event ref. Behavior does not change.

### 6.2 `release.yml` job graph

```
gate (uses ./.github/workflows/gate.yml, ref = tag)
  └── build  (needs: gate)
        ├── pypi  (needs: build)
        └── ghcr  (needs: build)      ← today ghcr has no needs
```

```yaml
concurrency:
  group: publish-${{ github.event.inputs.tag || github.ref_name }}
  cancel-in-progress: false

jobs:
  gate:
    if: >-
      (github.event_name == 'push' && startsWith(github.ref_name, 'v0.'))
      || (github.event_name == 'workflow_dispatch' && startsWith(github.event.inputs.tag, 'v0.'))
    permissions:
      contents: read
    uses: ./.github/workflows/gate.yml
    with:
      ref: ${{ github.event.inputs.tag || github.ref }}

  build:
    needs: gate
    # existing `if:` unchanged
    ...

  pypi:
    needs: build
    # unchanged apart from pins

  ghcr:
    needs: build
    # existing `if:` unchanged
    ...
```

Notes:
- Top-level `permissions: {}` stays. The `gate` job grants `contents: read`, which is the ceiling for the called workflow.
- The concurrency group prefix **must be `publish-`** and must differ from gate's `gate-…` prefix (§8). Otherwise the called gate and the caller could share a group and deadlock or cancel each other.
- A tag push will still also trigger `gate.yml` directly through `push:`. This duplicate run is accepted. `push` triggers are not changed, because v1.x Action tags rely on them.

---

## 7. `.github/dependabot.yml`

```yaml
version: 2
updates:
  - package-ecosystem: "uv"            # updates pyproject.toml + uv.lock together
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
      timezone: "Etc/UTC"
    cooldown:
      default-days: 7
    open-pull-requests-limit: 5
    groups:
      python-minor-patch:
        update-types: ["minor", "patch"]
    labels: ["dependencies", "python"]

  - package-ecosystem: "npm"           # pnpm-lock.yaml in web/
    directory: "/web"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
      timezone: "Etc/UTC"
    cooldown:
      default-days: 7
    open-pull-requests-limit: 5
    groups:
      web-minor-patch:
        update-types: ["minor", "patch"]
    labels: ["dependencies", "javascript"]

  - package-ecosystem: "github-actions" # .github/workflows/* and root action.yml
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
      timezone: "Etc/UTC"
    groups:
      actions:
        patterns: ["*"]
    labels: ["dependencies", "ci"]

  - package-ecosystem: "docker"         # PYTHON_IMAGE / UV_IMAGE digests in Dockerfile
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
      timezone: "Etc/UTC"
    labels: ["dependencies", "docker"]
```

- **`uv` replaces `pip`.** The `pip` ecosystem would bump `pyproject.toml` without touching `uv.lock`, and every one of those PRs would fail `uv sync --locked`. The `uv` ecosystem updates both files together.
  - Fallback: if the `uv` ecosystem is not available on the repo plan, use `pip` and add a CI note that maintainers must run `uv lock` on Dependabot PRs.
- **`docker` was not in the original request.** I added it because the Dockerfile pins base images by digest, and nothing else keeps those digests current.
- **Root `action.yml` coverage:** check after merge that Dependabot picks it up with `directory: "/"`. If it doesn't, change that entry to `directories: ["/", "/.github/workflows"]`.

---

## 8. `gate.yml`: permissions, concurrency, caches

### Top of file

```yaml
name: gate

on: { ...see §6.1... }

permissions:
  contents: read

concurrency:
  group: gate-${{ github.workflow }}-${{ github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name == 'pull_request' || (startsWith(github.ref, 'refs/heads/') && github.ref != 'refs/heads/main') }}

env:
  UV_PYTHON_DOWNLOADS: never
  UV_LINK_MODE: copy
```

How the concurrency group behaves:
- In a called context, `github.workflow` evaluates to the caller's name (`release`). The group becomes `gate-release-refs/tags/v0.x.y`, which differs from both the direct run (`gate-gate-refs/tags/v0.x.y`) and the release group (`publish-…`). Nothing collides.
- Runs are never cancelled on `main` or on tags. Superseded runs are cancelled on PRs and feature branches.

### Caches

| Tool | Mechanism | Key inputs |
|---|---|---|
| uv | `astral-sh/setup-uv` with `enable-cache: true`, `cache-dependency-glob: "uv.lock"`, `cache-suffix: "py${{ matrix.python-version \|\| '3.12' }}-${{ github.job }}"`, `version: "X.Y.Z"` | runner OS + uv.lock hash + suffix (the action builds the key automatically) |
| pnpm | `actions/setup-node` with `cache: pnpm`, `cache-dependency-path: web/pnpm-lock.yaml` | Already present. Keep it. |
| pip | `actions/setup-python` with `cache: pip`, `cache-dependency-path: pyproject.toml` | **`web-build` only.** Used by the unlocked wheelenv smoke install. |

`setup-python` in uv jobs gets **no** `cache:` input. The uv cache covers those jobs.

---

## 9. Step order per job (after change)

`<pin>` means the SHA-pinned `uses:` from §3. `setup-uv` always gets `with: { version: "X.Y.Z", enable-cache: true, cache-dependency-glob: "uv.lock", cache-suffix: … }`.

### gate.yml

**lint** (3.12)
- `checkout <pin>` (`ref: ${{ inputs.ref }}`)
- `setup-python <pin>` 3.12
- `setup-uv <pin>`
- `uv sync --locked --extra dev --python 3.12`
- `echo "$PWD/.venv/bin" >> "$GITHUB_PATH"`
- `ruff check` → `ruff format --check` → `mypy src` (unchanged)

**test** (matrix 3.11 / 3.12 / 3.13, `fail-fast: false`, `name: test (${{ matrix.python-version }})`)
- `checkout <pin>`
- `setup-python <pin>` `${{ matrix.python-version }}`
- `setup-uv <pin>`
- `pnpm/action-setup <pin>` (version 10): `if: matrix.python-version == '3.12'`
- `setup-node <pin>` (22, pnpm cache): `if: matrix.python-version == '3.12'`
- `uv sync --locked --extra dev --python "${{ matrix.python-version }}"`
- add `.venv/bin` to `GITHUB_PATH`
- "Web unit tests" (`pnpm install --frozen-lockfile && pnpm test`): `if: matrix.python-version == '3.12'`
- `pytest -q -m "not integration"` (unchanged)

**integration** (matrix 3.11 / 3.12 / 3.13, `fail-fast: false`, `name: integration (${{ matrix.python-version }})`)
- `checkout <pin>`
- `setup-python <pin>` matrix
- `setup-uv <pin>`
- `uv sync --locked --extra dev --python "${{ matrix.python-version }}"`
- add `.venv/bin` to `GITHUB_PATH`
- `pytest -q -m integration tests/integration` (unchanged)

**gate** (3.12)
- `checkout <pin>`
- `setup-python <pin>` 3.12
- `setup-uv <pin>`
- `uv sync --locked --python 3.12` (core only)
- add `.venv/bin` to `GITHUB_PATH`
- "core install pulls no ui/docs extras": same names and same exit condition; `importlib.metadata` replaces `pip freeze` (§5.2)
- all remaining steps unchanged and in the same order (`--help`, `checks show`, `example`, `ingest`, keyless exit 2, ui exit 2 + hint)

**web-build** (3.12)
- `checkout <pin>`
- `setup-python <pin>` 3.12, `cache: pip`, `cache-dependency-path: pyproject.toml`
- `setup-uv <pin>`
- `pnpm/action-setup <pin>` (10)
- `setup-node <pin>` (22, pnpm cache)
- "Build sdist and wheel with React UI": `uv build` then `python tests/assert_wheel_ui.py`
- "pip install wheel and serve UI without pnpm": unchanged, plus a comment that this is an intentionally unlocked end-user canary

**oss-surface** (3.12)
- `checkout <pin>`
- `setup-python <pin>` 3.12
- `setup-uv <pin>`
- `uv sync --locked --extra dev --python 3.12`
- add `.venv/bin` to `GITHUB_PATH`
- `pytest -q tests/test_oss_surface.py tests/test_dockerfile.py` (unchanged)

**docker**
- `checkout <pin>` (`ref: ${{ inputs.ref }}`)
- build, inspect and run steps unchanged. The image now installs from `uv.lock` (§5.3).

### release.yml

**gate** (new): `uses: ./.github/workflows/gate.yml`, `with.ref` set to the tag, `permissions: contents: read`, same `if:` as `build`.

**build**
- `needs: gate`
- `checkout <pin>` (`ref: tag`)
- `setup-python <pin>` 3.12
- `setup-uv <pin>`
- `pnpm/action-setup <pin>`
- `setup-node <pin>`
- "Build React UI into the wheel": `uv build` → `ls -la dist` → `python tests/assert_wheel_ui.py`
- `upload-artifact <pin>`

**pypi**
- `needs: build` (unchanged)
- `download-artifact <pin>`
- `pypa/gh-action-pypi-publish <pin>` (`skip-existing: true` unchanged)

**ghcr**
- **`needs: build`** (new)
- `checkout <pin>`
- `docker/login-action <pin>`
- "Build and push runtime image" unchanged

### skillgate-action.yml

**action**: `checkout <pin>`. Nothing else changes.

### action.yml (composite)

- `actions/setup-python <pin>` (Python `3.11` unchanged). Nothing else changes.

---

## 10. Acceptance criteria

**Lockfile**
- [ ] `.gitignore` no longer contains `uv.lock`, and `git ls-files uv.lock` returns the file.
- [ ] `uv lock --check` passes on the committed tree.
- [ ] No workflow job installs project deps with `pip install -e`. The only remaining `pip install` is the intentional wheelenv canary in `web-build`.
- [ ] Every uv install in CI uses `--locked`.

**Pins**
- [ ] This returns no lines:
  ```bash
  grep -rnE '^\s*-?\s*uses:\s*[^./][^@]*@' .github/workflows action.yml | grep -vE '@[0-9a-f]{40} # v[0-9]+\.[0-9]+\.[0-9]+$'
  ```
- [ ] Each SHA was resolved with `gh api repos/<o>/<r>/commits/<tag> --jq .sha` and matches its comment.
- [ ] `pypa/gh-action-pypi-publish` is pinned to a release **tag** SHA, not the `release/v1` branch.
- [ ] The Dockerfile `UV_IMAGE` is pinned by `@sha256:`, and its uv version equals the `setup-uv` `version:` input.

**Matrix**
- [ ] `test` and `integration` each report three green checks (3.11, 3.12, 3.13).
- [ ] Web unit tests run exactly once per gate run (in `test (3.12)`).
- [ ] `lint`, `gate`, `web-build` and `oss-surface` run on 3.12 only.
- [ ] `pyproject.toml` classifiers include 3.11, 3.12 and 3.13, and `requires-python` is still `>=3.11`.

**gate.yml**
- [ ] It has top-level `permissions: contents: read`.
- [ ] Its concurrency group starts with `gate-`. Pushing twice to a PR cancels the first run; pushing to `main` or a tag never cancels.
- [ ] The uv cache restores on a second run ("Cache restored" appears in the setup-uv log), and the pnpm cache still restores.
- [ ] All seven jobs still exist and are green, and no assertion was removed or relaxed.

**Release**
- [ ] `release.yml` graph: `gate → build → {pypi, ghcr}`. `ghcr` has `needs: build`.
- [ ] Dry-run check: on a fork or a throwaway `v0.0.0-test` tag (repo guard prevents publish), a deliberately failing test stops `build`, `pypi` and `ghcr` from starting.
- [ ] A `workflow_dispatch` with `tag: v0.x.y` checks out that tag inside the called gate jobs (confirm in the checkout step log).
- [ ] The top-level `permissions: {}` in `release.yml` is unchanged, and `pypi` still has only `id-token: write`.

**Docker**
- [ ] `docker build -t skillgate:test --target runtime .` succeeds, and the `docker` CI job is green (non-root, entrypoint/cmd, keyless exit 2).
- [ ] `pytest -q tests/test_dockerfile.py` passes.
- [ ] Editing `uv.lock` so it is inconsistent with `pyproject.toml` makes the Docker build fail at `uv sync --locked`.

**Dependabot**
- [ ] `.github/dependabot.yml` validates (it shows under Insights → Dependency graph → Dependabot with no config errors).
- [ ] The uv, npm (`/web`), github-actions and docker ecosystems all appear.

**Local**
- [ ] `ruff check`, `ruff format --check`, `mypy src` and `pytest -q` pass locally after `uv sync --locked --extra dev`.
- [ ] The `pre-commit` hooks pass (`check-yaml` covers the new and modified YAML).
- [ ] Branch protection required checks are updated to the matrix job names (§4).

---

## 11. Out of scope

- Any change under `src/`: CLI, gate, judges, local UI, `skillgate_build.py`.
- Security hardening and retry behavior (#75), typing and mypy config (#76).
- Fixing, skipping, deleting or re-marking tests. Removing dead code.
- Loosening any CI check, or removing or merging any CI job. Duplicate runs of `gate.yml` on tag pushes are accepted.
- Major-version upgrades of actions (e.g. checkout v5+, setup-python v6+). Dependabot proposes these after merge.
- Upgrading Node, pnpm or Python minor versions used in CI. This includes the `pnpm@9.15.9` `packageManager` field vs action-setup `version: 10` mismatch in `web/`, which is noted but not touched.
- Adding Docker Buildx/GHA layer caching, SBOMs, provenance or image signing for GHCR.
- A `uv-pre-commit` lock hook. CI `--locked` is the drift gate for this PR.
- Changing `push`/`pull_request` triggers, or the `skillgate-action.yml` job logic.
- `ci/cloud-web-pnpm-lock.yaml`, and anything belonging to the private `skillgate-ai` repo.
