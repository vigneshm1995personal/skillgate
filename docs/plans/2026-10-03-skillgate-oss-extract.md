# Skill Gate OSS extract + Docker — Implementation Plan

> **Historical (2026-10-03).** This plan described the OSS extract. It is not current product docs. Skill Gate 0.5 is live-only (no demo harness). See [`0.5-decisions.md`](0.5-decisions.md).

> **This document is Phase 1 (plan only) for the public staging repo `vigneshm1995personal/skillgate`.** Do **not** copy application code from `skillgate-ai` in this PR. Do **not** flip this repo public. Do **not** implement `check`, PyPI, GHCR, or the extract until Phase 2 is requested.

**Goal:** Land a concrete, allowlist-based extract of the **local gate** into this repo (clean history, Apache-2.0) plus a production-quality Docker image whose `ENTRYPOINT` is `skillgate` and whose default argv is `check` (never `serve`).

**Parent (locked — do not override):** [`docs/plans/2026-10-03-oss-public-private-split.md`](https://github.com/vigneshm1995personal/skillgate-ai/blob/cursor/oss-public-private-split-516c/docs/plans/2026-10-03-oss-public-private-split.md) on private `vigneshm1995personal/skillgate-ai` ([PR #152](https://github.com/vigneshm1995personal/skillgate-ai/pull/152), branch `cursor/oss-public-private-split-516c`; not on `main` as of 2026-10-04). Inspected private tree: `main` @ `6372ba1` (`feat(web): eval rows then stamp (#151)`).

**Decision rule (locked):** if a feature cannot work as **one pack on disk** plus `skillgate check` exiting **0 or 1** with **no Skill Gate account**, it is cloud or paid and must not become the only path. Deterministic fixture checks are unlimited and must not require Gateway or Jev.

**Docker skills (locked for the image):** **docker-project-foundations** (root `Dockerfile` + `compose.yaml` + `.dockerignore`; create `.dockerignore` first; Compose not host installs) and **docker-build-strategies** (multi-stage, slim pin, BuildKit cache mounts, non-root user, no secrets in `ARG`/`ENV`/`COPY`, `# syntax=docker/dockerfile:1`, exec-form `ENTRYPOINT`). Cite those names in the Phase 2 Docker PR.

---

## 0. What this staging repo is

| Fact | Value |
| --- | --- |
| GitHub | `vigneshm1995personal/skillgate` (PRIVATE staging as of 2026-10-04) |
| After first clean tag | Flip **this** repo public. Never flip `skillgate-ai`. |
| License | Apache-2.0 |
| Private hosted app | stays `vigneshm1995personal/skillgate-ai` |
| Extract style | **Allowlist copy onto a new history.** Not `git filter-repo` of private history. |
| This PR | `docs/plans/2026-10-03-skillgate-oss-extract.md` + README pointer. No product code. |

---

## 1. Locked product names (extract-time check, done 2026-10-04)

Parent §2 left PyPI as “keep `skillgate-ai` **or** new `skillgate` if the name is free.” Checked live:

| Artifact | Decision | Why |
| --- | --- | --- |
| Public GitHub repo | `vigneshm1995personal/skillgate` | Already created; this tree. |
| Private GitHub repo | `vigneshm1995personal/skillgate-ai` | Hosted app; SIWV / vault / Neon / Vercel Sandbox. |
| **PyPI distribution** | **`skillgate-ai`** | [`pypi.org/pypi/skillgate`](https://pypi.org/pypi/skillgate) is **taken** (v1.2.3, proprietary, [skillgate-io/skillgate](https://github.com/skillgate-io/skillgate) — a different product). [`pypi.org/pypi/skillgate-ai`](https://pypi.org/pypi/skillgate-ai) is **404 / free**. Do **not** squat `skillgate`. |
| Import package | `skillgate_ai` | Private app already imports it; quieter first bump. |
| CLI scripts | `skillgate` and `skillgate-ai` (both → `skillgate_ai.cli:app`) | Same as private `pyproject.toml` today. The **command** is `skillgate check`. |
| GHCR image | `ghcr.io/vigneshm1995personal/skillgate:vX.Y.Z` | Same SemVer as PyPI. First GHCR push defaults **private** — flip the package public after the first tag. |

Docs and `pip install` strings in the first milestone **must** say `skillgate-ai`, not `pip install skillgate` (that would install the other project).

---

## 2. First OSS milestone (acceptance — Phase 2)

A stranger with **no Skill Gate account**, in about 10 minutes:

```bash
pip install skillgate-ai
skillgate check skills/pdf-sabotaged    # exit 1
# documented one-liner: copy SKILL.md from skills/pdf (or follow quickstart)
skillgate check skills/pdf              # exit 0
```

Docker (GHCR after first tag; local `docker compose` before publish):

```bash
docker run --rm -v "$PWD/skills/pdf:/pack:ro" \
  ghcr.io/vigneshm1995personal/skillgate:vX.Y.Z
# ENTRYPOINT skillgate; default CMD check /pack → exit 0

docker run --rm -v "$PWD/skills/pdf-sabotaged:/pack:ro" \
  ghcr.io/vigneshm1995personal/skillgate:vX.Y.Z
# exit 1
```

Copy-paste GitHub Action (rung 1 — not Marketplace yet):

```yaml
- uses: actions/setup-python@v5
  with: { python-version: "3.12" }
- run: pip install skillgate-ai==X.Y.Z
- run: skillgate check .
```

Working directory is the skill pack. Exit 1 fails the job. No account. Det fixtures unlimited (demo harness; no `AI_GATEWAY_API_KEY`, no Jev).

Docs: one public `README` + `docs/quickstart.md` (10 minutes, no sign-up, no Neon, no SIWV). BYO key / local model only if they want a **judge** beyond deterministic fixtures.

Out of this milestone: Marketplace `action.yml`, bundled model weights, hosted free-tier, pack viewer SPA, generated-check drafts, Vercel Sandbox, making `skillgate-ai` public.

---

## 3. Never copy (deny list)

These stay **only** in `skillgate-ai`. Copying any of them into this repo (tree, README screenshot, Actions log, or Docker layer) is a failed extract.

### 3.1 Files / trees (user lock + parent §5)

| Path at `6372ba1` | Why |
| --- | --- |
| `src/skillgate_ai/auth_siwv.py` | Sign in with Vercel |
| `src/skillgate_ai/vault.py` | Fernet `user_secrets`; `SKILLGATE_SECRETS_KEY` |
| `src/skillgate_ai/store_postgres.py` | Neon SoR |
| `src/skillgate_ai/store.py` | Mini SQLite **or** Neon when `DATABASE_URL` is set. OSS SoR is pack `evals/history/` JSONL, not this module. |
| `src/skillgate_ai/remote_harness/` (entire dir, including `vercel_sandbox.py`, `sandbox_queue_poller.py`) | Hosted microVM / staging / Cursor Cloud / Codex remote |
| `src/skillgate_ai/eval_slice.py` | Hobby Function maxDuration workaround |
| `src/skillgate_ai/web.py` | FastAPI hosted dashboard (~118 KB) |
| `src/skillgate_ai/web/` | Jinja/static bundled with the wheel |
| `web/` | React/shadcn SPA |
| `Dockerfile.vercel` | Fluid Compute Function image |
| `src/skillgate_ai/author.py`, `stage_b.py`, `wizard.py` | Assist / generated-check drafts UX |
| `src/skillgate_ai/jev_qa.py` | Hosted Jev client (`POST https://ai-gateway.vercel.sh/v1/evaluate`) |
| `src/skillgate_ai/deploy_git.py` | Git-publish PAT path (`SKILLGATE_SKILLS_GITHUB_TOKEN`) |
| `scripts/warm-sandbox-snapshot.py`, `scripts/vcr-prune-images.py`, `scripts/finalize-orphan-run.py` | Hosted sandbox ops |
| `.env.example` **as-is** | Documents SIWV, vault, Neon, `VERCEL_TOKEN`, git-publish. Rewrite a stripped OSS file instead. |
| `docs/vercel-hosting.md`, `docs/neon-store.md`, `docs/jev-outcome-judge.md` | Hosted runbooks |
| `docs/plans/2026-10-01-settings-neon-siwv-vault.md` and other hosted-only plans | Private product |
| `docs/brand/`, `docs/checks-ui-mock/` | Hosted UI |
| `.cursor/`, `.agents/` | Private agent config |

### 3.2 Tests that must not ship

`tests/test_auth_siwv.py`, `test_author.py`, `test_deploy_git.py`, `test_eval_slice.py`, `test_jev_qa.py`, `test_sandbox_queue_poller.py`, `test_settings_vault.py`, `test_store.py`, `test_store_postgres.py`, `test_remote_harness.py`, `test_vercel_sandbox_harness.py`, `test_vercel_dockerfile.py`, `test_web.py`, `test_web_eval_slice.py`, `test_wizard.py`, `test_stage_b.py`, `test_suggest_skill.py`, `test_orphan_sandbox_reaper.py`, `test_durable_live_snapshot.py`, `test_run_fencing.py`, `test_preselect_skill.py`, `test_pack_inherit_ui.py`, `test_model_catalog.py`.

### 3.3 Secrets / env names (never in public `.env.example`, README, or image)

`VERCEL_APP_CLIENT_ID`, `VERCEL_APP_CLIENT_SECRET`, `SKILLGATE_SIWV_ALLOWLIST`, `SKILLGATE_OWNER_EMAIL`, `SKILLGATE_AUTH_OPEN`, `SKILLGATE_SECRETS_KEY`, `DATABASE_URL` / `POSTGRES_*`, `db-creds.env`, `VERCEL_TOKEN` / `VERCEL_OIDC_TOKEN`, `SKILLGATE_SKILLS_GITHUB_TOKEN`, production `SENTRY_DSN`, any ciphertext.

### 3.4 Current private Docker (do not copy)

Private root `Dockerfile` @ `6372ba1` (283 bytes):

```
FROM python:3.12-slim
… pip install .
ENTRYPOINT ["skillgate-ai"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8477"]
```

That image **serves the UI**. OSS replaces it entirely (see §7). Do not copy it.

---

## 4. Allowlist (copy from `skillgate-ai` @ `6372ba1`, then strip)

Copy **file contents** from a checkout of private `main` (or a later pin if `main` moved). Do **not** copy `.git`. Each file below is either **copy-then-strip** or **copy-as-is**. New files are marked **new**.

### 4.1 Package metadata / license

| Path | Action |
| --- | --- |
| `LICENSE` | Copy Apache-2.0 text (copyright line “Skill Gate AI contributors” is fine). |
| `pyproject.toml` | Copy then **rewrite** (§5). |
| `.gitignore` | Copy then drop `db-creds.env` commentary that implies Neon; keep `.env`, `.skillgate/`, `evals/history/*.jsonl` (except `.gitkeep`). |

### 4.2 Public Python package (`src/skillgate_ai/`) — copy then strip hosted hooks

**Copy (local-gate shaped; strip only comments/imports that mention hosted):**

| File | Notes |
| --- | --- |
| `__init__.py` | Keep `__version__`; bump with SemVer on first public tag (start `0.3.0` or keep `0.2.0` and tag `v0.2.0` — prefer **`0.3.0`** so the public wheel is not confused with the mixed private 0.2.0). |
| `case_pack.py` | Schema `Literal[1]`. Trust path. |
| `pack.py` | Skill folder blob store; skip `.skillgate/` and `evals/goldens/` on Deploy copy. |
| `ingest.py` | SKILL.md / agentskills. |
| `suite.py` | YAML suite loader (needed until pdf twins are pack-local; keep after). |
| `fixture_bind.py` | Inherit + authenticity / gate decision. Keep **schema and scoring**; drop any Start-Evaluations-only UI helpers if they import `web`. |
| `scorers.py` | `skill_trigger`, `task_completion`, `rubric`. Det path. |
| `sandbox.py` | Tempdir default; `--sandbox docker` optional. Drop `SKILLGATE_SECRETS_KEY` from the blocked-env set only if vault is gone (harmless to leave the name). |
| `errors.py` | Keep. `AuthorError` can stay unused or be deleted. |
| `eval_config.py` | Run stamp (model/timeout/temperature). |
| `demo_files.py` | Generates demo PDFs via reportlab (pdf fixtures are gitignored in private). |
| `report.py` | CLI + GitHub summary. Keep. |
| `live.py` | `RunControl` / skip / kill. Local CLI needs it. Not the hosted snapshot poller. |
| `metrics.py`, `spans.py`, `usage.py` | Local report fields. |
| `advice.py` | CLI “why/fix” on red. Keep. |
| `paths.py` | `SKILLGATE_ROOT` + `skills/`+`evals/` discovery. Extend so a **single skill pack directory** (SKILL.md + `evals/`) counts as root for `check .`. |
| `ingest` dependents above | — |

**Copy and surgically strip:**

| File | Strip |
| --- | --- |
| `cli.py` | Today: `version`, `ingest`, `run`, **`serve`**, `list`. **Delete `serve`** (it `uvicorn.run("skillgate_ai.web:app")`). **Add `check`** as the 0/1 command (alias of today’s `run` semantics: `typer.Exit(0 if report.passed else 1)` + `--expect-fail`). `_persist_cli_eval` must **not** call `store.record_eval`; write pack `evals/history/` via new `history.py`. Drop `init_sentry` as a required boot (optional extra). Do not mention Settings / SIWV in help text. |
| `config.py` | Today `get_llm_config()` imports **`vault.resolve_secret`**. Replace with `os.environ.get`. Stop loading `db-creds.env`. Keep `.env` for BYOLLM keys. Rewrite `missing_key_error` hints (no “open Settings”, no hosted). Gateway URL may remain as **one optional BYO HTTP base** the **user** owns — it must not be the only live path, and **det/demo must work with no key**. |
| `engine.py` | Today imports `jev_qa.run_jev_outcome_judge` and `remote_harness.sandbox_queue_poller.SandboxPollPending`. **Delete both.** Inject a `Judge` protocol (new `judge.py`). Default judge: **skip** (det-only). No `JEV_ENDPOINT`. Drop `resume_sandbox_poll` / chunked-eval parameters from the public signature **or** no-op them with a comment that hosted injects them privately. |
| `harness.py` | Keep: demo, local `agent` / `codex exec`, BYO HTTP with the **user’s** key. Strip: anything that **requires** `AI_GATEWAY_API_KEY` for det; any `remote_harness` import; Vercel-only auto routing. `_gateway_complete` (if kept) must be a generic OpenAI-compatible POST to `AI_GATEWAY_BASE_URL` **or** user `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` — never fail the demo path. |
| `deploy.py` | Keep Cursor / Claude / Codex **local copy**. Strip `from skillgate_ai.deploy_git import git_publish_status`, `VERCEL=1` hosted messaging in `deploy_status`, git mode. Optional CLI: `skillgate deploy <pack> --target cursor`. |
| `observability.py` | Parent allows the SDK **if it no-ops without a DSN**. Make `import sentry_sdk` **lazy** so the public wheel does **not** require `sentry-sdk`. Never document a DSN in OSS `.env.example`. Alternative (cleaner): stub breadcrumbs as no-ops in OSS and leave Sentry only in the private app. **Prefer the stub** so `pip install skillgate-ai` stays small. |
| `catalog.py` | Hosted `GET /api/status` helper. **Skip** for first milestone (CLI `list` can scan `skills/` directly). |

**Do not copy (paid / hosted-shaped even if pure Python):**

`regression.py`, `suggest_skill.py`, `model_catalog.py` — parent lists “regression vs last green” as paid product. Revisit after milestone 1.

### 4.3 New modules (not in private tree)

| Path | Role |
| --- | --- |
| `src/skillgate_ai/judge.py` | `Judge` protocol: `(goal, artifacts, transcript_tail) -> {passed, cells}`. Implementations: `SkipJudge` (default), later `ByoHttpJudge`. Private app injects Jev **outside** this repo. |
| `src/skillgate_ai/history.py` | Append-only JSONL under `<pack>/evals/history/`. Same report JSON as `report_to_dict`. Gitignore `*.jsonl`; ship `.gitkeep` + short README. |

### 4.4 Seed skills (first milestone = pdf twins)

Private `skills/pdf` and `skills/pdf-sabotaged` at `6372ba1` have **only** `SKILL.md`, `requirements.txt`, `scripts/*.py`. Cases live in **repo-root** `evals/pdf.yaml` and `evals/pdf-sabotaged.yaml`. Fixtures PDFs are **generated** by `demo_files.ensure_demo_pdfs` (gitignored `evals/fixtures/*.pdf`).

**Extract action:**

1. Copy `skills/pdf/**` and `skills/pdf-sabotaged/**` as-is.
2. **Materialize pack-local SoR** (parent §10.1) as part of Phase 2, not a later nice-to-have for the milestone:
   - `skills/pdf/evals/cases.yaml` — migrate from `evals/pdf.yaml` (`schema: 1`, skill-relative fixture paths).
   - `skills/pdf-sabotaged/evals/cases.yaml` — same from `evals/pdf-sabotaged.yaml`.
   - `evals/fixtures/` generated PDFs **or** commit generated tiny PDFs under each pack’s `evals/fixtures/` so `check` works offline without a writeable global `evals/`.
   - `evals/goldens/` as needed; `evals/history/.gitkeep`.
3. Keep loading **today’s** root YAML during a short compatibility window **inside Phase 2** until `check <skill-dir>` works; then delete root `evals/*.yaml` from the public tree so the pack is the only SoR.

**Optional same-PR-or-follow-up (not required for red→green pdf):** `skills/csv-clean`, `standup-notes`, `report-writer`, `receipt-photo` already have pack-local `evals/cases.yaml` + fixtures + goldens. Copy if they contain no secrets (they are sample skills). `evals/fixtures/IMG_6186.jpeg` is a real photo used by receipt-photo — include only if that skill ships.

### 4.5 Tests to copy (then strip hosted imports)

`tests/conftest.py`, `helpers.py`, `test_case_pack.py`, `test_cli.py`, `test_deploy.py`, `test_engine.py`, `test_eval_config.py`, `test_fixture_bind.py`, `test_harness.py`, `test_ingest.py`, `test_live.py`, `test_metrics.py`, `test_pack.py`, `test_pack_trust.py`, `test_sandbox.py`, `test_spans.py`, `test_usage.py`, `test_advice.py`, `test_diverse_example_skills.py` (only if those skills ship).

Add **new** `tests/test_check_cli.py`, `tests/test_history.py`, `tests/test_judge.py`, `tests/test_dockerfile.py` (assert `ENTRYPOINT`/`CMD`/`USER`, assert **not** `serve`).

### 4.6 Local sandbox image (optional, OSS)

`Dockerfile.sandbox` — copy then rewrite per **docker-build-strategies** (pin, non-root if it executes user code). Used by `--sandbox docker`, **not** the gate CLI image.

### 4.7 Docs to write in this public repo (not copy private hosted docs)

| Path | Content |
| --- | --- |
| `README.md` | 10-minute no-account path; `pip install skillgate-ai`; Docker; copy-paste Action. Point at `docs/quickstart.md`. |
| `docs/quickstart.md` | Red pdf-sabotaged → green pdf. |
| `docs/pack.md` | `evals/cases.yaml` schema 1, fixtures, goldens, history. |
| `.env.example` | **Only** `CURSOR_API_KEY`, `CODEX_API_KEY` / `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, optional `AI_GATEWAY_API_KEY` as BYO, `SKILLGATE_SANDBOX`, `SKILLGATE_DOCKER_IMAGE`. No SIWV/Neon/vault. |

---

## 5. Hosted imports / deps to strip

### 5.1 `pyproject.toml` rewrite

Private runtime deps @ `6372ba1`:

```
typer, rich, pyyaml, pydantic, fastapi, uvicorn[standard], python-multipart,
jinja2, httpx, python-dotenv, pypdf, reportlab, sentry-sdk[fastapi],
psycopg[binary], cryptography
```

| Keep (public required) | Drop (hosted) |
| --- | --- |
| `typer`, `rich`, `pyyaml`, `pydantic` | `fastapi`, `uvicorn[standard]`, `python-multipart`, `jinja2` |
| `httpx` (BYO HTTP judge / optional LLM harness) | `psycopg[binary]` |
| `python-dotenv` | `cryptography` (vault) |
| `pypdf`, `reportlab` (pdf scorers + demo fixtures) | `sentry-sdk[fastapi]` as **required** |

`[project.optional-dependencies]`: `dev = ["pytest", "ruff"]`. No `web` extra.

`[project.scripts]`: keep both `skillgate` and `skillgate-ai`.

`[tool.setuptools.package-data]`: **delete** `web/templates/*` / `web/static/*`.

`name = "skillgate-ai"` (PyPI — see §1). `requires-python = ">=3.11"` (unchanged).

### 5.2 Import graph that must be gone after strip

A public `python -c "import skillgate_ai.cli"` must **not** import:

`skillgate_ai.auth_siwv`, `.vault`, `.store`, `.store_postgres`, `.web`, `.eval_slice`, `.jev_qa`, `.author`, `.wizard`, `.stage_b`, `.deploy_git`, `.remote_harness`.

Enforcement: `tests/test_oss_surface.py` walks `src/skillgate_ai` with AST and fails on those module names.

`config.get_llm_config` must not call `vault.resolve_secret`.

`engine.run_eval` must not import `remote_harness` or `jev_qa`.

`cli` must not import `uvicorn` or `skillgate_ai.web`.

---

## 6. Clean-history extract procedure (Phase 2)

Do **not** run `git filter-repo` on `skillgate-ai`. Private history contains SIWV, vault, Neon URLs in diffs, `Dockerfile.vercel`, ops scripts. A clone of a publicized private repo includes **all versions of every file**.

1. Keep `skillgate-ai` **private** forever (parent §7).
2. Keep **this** repo private until the first scanned tag.
3. From a throwaway worktree of `skillgate-ai` pinned to a SHA (start `6372ba1` or later `main`):

   ```bash
   # illustrative — Phase 2 writes the real script
   rsync -a --files-from=allowlist.txt skillgate-ai/ skillgate/
   ```

4. Commit on this repo as **new commits** (orphan already exists: current `main` is an empty README). Do not `git subtree` / submodule the private tree.
5. Run the strip checklist (§5) in the same PR series as the copy, **before** any tag.
6. Enable secret scanning + push protection on this repo.
7. Scan the first tag (`gitleaks` / `trufflehog` / `git grep` for `sk-`, `postgres://`, `SKILLGATE_SECRETS_KEY`, `VERCEL_APP_CLIENT`).
8. Then Settings → Change repository visibility → **Public** on **`skillgate` only**.

If someone later wants OSS-only blame, that is a separate, optional `git filter-repo --sensitive-data-removal` **from an allowlisted export**, never from the private repo’s full history.

---

## 7. Docker design (must be perfect)

Follow **docker-project-foundations** and **docker-build-strategies**. Private `CMD ["serve"]` is the anti-pattern.

### 7.1 Files (foundations: always these three, at repo root)

| File | Role |
| --- | --- |
| `.dockerignore` | **Create first** so the build context is small and secret-free. |
| `Dockerfile` | Multi-stage CLI image. |
| `compose.yaml` | Local one-command `check` (no host Python). Name is `compose.yaml`, not `docker-compose.yml`. |

Optional: `Dockerfile.sandbox` (task isolation), `compose.override.yaml` later. No `Dockerfile.vercel`.

OSS `check` has **no Postgres/Redis**. Do **not** add a database service “because the foundations example has one.” Foundations says: prefer Compose **for dependencies the project actually needs**; do not tell the user to `apt install` those. Here the only service is the gate (plus optional sandbox image).

### 7.2 `.dockerignore` (minimum)

From **docker-build-strategies** / foundations assets, plus this product:

- `.git/`, `.github/`, `.vscode/`, `.idea/`
- `__pycache__/`, `.venv/`, `*.egg-info/`, `dist/`, `build/`, `.pytest_cache/`
- `**/.npmrc`, `.env`, `.env.*`, `*.pem`, `*.key`, `db-creds.env`
- `docs/`, `*.md` (keep `README.md` if `pyproject` `readme =` needs it at **build** time — if so, do **not** exclude `README.md` / `LICENSE`; they are required for `pip install .`)
- `tests/` (runtime image does not need them; CI builds tests on the host/Compose `dev` stage)
- never exclude `src/`, `pyproject.toml`, `skills/` (sample packs can be omitted from the **image** if users always bind-mount `/pack` — prefer **omit skills from the runtime image** to keep it small; ship skills in git for `pip`/`clone` users)

### 7.3 `Dockerfile` (build-strategies)

Lock:

1. First line: `# syntax=docker/dockerfile:1`
2. Named stages: `FROM python:3.12-slim-bookworm AS build` then `AS runtime` (and `AS dev` for Compose live-reload). **Pin the digest at extract time** (`python:3.12-slim-bookworm@sha256:…`). Never `latest`. 3.12 matches private CI (`setup-python 3.12`) and `requires-python >=3.11`. Do not jump to the skill’s 3.13 example without a test pass.
3. `WORKDIR` set before `COPY`/`RUN`.
4. Build: `python -m venv /opt/venv`; `ENV PATH="/opt/venv/bin:$PATH"`.
5. Install deps **before** full source copy. `pyproject.toml` has no `requirements.txt` — bind-mount the manifest(s):

   ```dockerfile
   RUN --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
       --mount=type=bind,source=README.md,target=README.md \
       --mount=type=bind,source=LICENSE,target=LICENSE \
       --mount=type=cache,target=/root/.cache/pip \
       pip install --no-compile .
   ```

   Then `COPY` `src/` and `pip install --no-deps --no-compile .` (or copy src before the second install). Goal: dependency layer stays cached when only `engine.py` changes.
6. No `ARG`/`ENV` for tokens. No `COPY` of `.env`. Public PyPI/GHCR build needs **no** BuildKit secret. If a private index appears later, `RUN --mount=type=secret`, never `ARG PIP_INDEX_URL`.
7. Runtime: same slim base. `addgroup --system --gid 1001 appgroup && adduser --system --uid 1001 --ingroup appgroup appuser`.
8. `COPY --from=build --link --chown=1001:1001` (numeric UID with `--link`, per build-strategies).
9. `USER appuser` **after** all file ops, **before** `ENTRYPOINT`.
10. **Do not `EXPOSE 8477`.** This is a CLI, not `serve`. The skill’s “add EXPOSE” rule is for listening servers; documenting a fake port would invite `CMD serve`.
11. `LABEL org.opencontainers.image.source=https://github.com/vigneshm1995personal/skillgate`
12. **`ENTRYPOINT ["skillgate"]`** (exec form).
13. **`CMD ["check", "/pack"]`** — default argv is `check`, **not** `serve`. Bind-mount the pack at `/pack`.

`docker run image` with `-v $PWD/skills/pdf:/pack:ro` runs `skillgate check /pack`. Overriding CMD (`docker run image version`) still uses ENTRYPOINT `skillgate`.

Non-root cannot write a read-only `/pack`. History JSONL: write to a writable mount (e.g. `/pack/evals/history` rw) **or** skip history when `/pack` is ro (document it). Prefer: compose mounts pack **rw** for local history; GHCR examples use `:ro` and skip history on `EACCES`.

### 7.4 `compose.yaml`

```yaml
services:
  skillgate:
    build:
      context: .
      dockerfile: Dockerfile
      target: runtime
    image: skillgate:local
    user: "1001:1001"
    volumes:
      - ${PACK:-./skills/pdf}:/pack
    # no ports — CLI exits
    # default ENTRYPOINT/CMD → skillgate check /pack
```

`PACK=./skills/pdf-sabotaged docker compose run --rm --no-TTY skillgate` must exit 1.

Dev target (foundations: one Dockerfile, `target: dev`): bind-mount `./src` for live edit; still non-root.

No datastore, no published ports, no `0.0.0.0`.

### 7.5 Verification (Phase 2, before merge)

From **docker-project-foundations** `checks/verification.md` and **docker-build-strategies** `checks/verification.md`:

- `.dockerignore`, `Dockerfile`, `compose.yaml` exist.
- `docker compose config --quiet`
- `docker buildx build -t skillgate:test .`
- `docker inspect` → `User` is `appuser` or `1001:1001`, **not** root; `Entrypoint` is `["skillgate"]`; `Cmd` is `["check","/pack"]`.
- `grep` Dockerfile: no `COPY` of `.env` / `.pypirc`; no `ARG`/`ENV` TOKEN|KEY|SECRET|PASSWORD.
- Image size: Python slim baseline **< 250 MB** (skill table). Fail the PR if the runtime stage still contains pytest/ruff or `web/`.
- Functional: `docker compose run` pdf → 0; pdf-sabotaged → 1; **no** Gateway env.

---

## 8. Public CI (this repo, after extract)

| Job | What |
| --- | --- |
| `test` | `pytest` pack/schema/scorers/cli/judge/history only |
| `gate` | `skillgate check skills/pdf` exit 0; `skillgate check skills/pdf-sabotaged` exit 1 (or `--expect-fail` → 0) |
| `docker` | build; same 0/1 via `docker run` |
| `oss-surface` | AST deny-list (§5.2) |
| `release` | **later** on tag: Trusted Publishing to PyPI (`skillgate-ai`) + GHCR; then flip GHCR visibility public |

No SIWV, Neon, or Vercel Sandbox secrets. Live Cursor/Codex keys optional and **never** required for merge (det/demo).

Copy-paste workflow lives in `docs/quickstart.md` (rung 1). Root `action.yml` is **after** CLI is stable (parent §9.3 rung 2).

---

## 9. Private app follow-up (not this repo)

Tracked so Phase 2 extract does not leave `skillgate-ai` copying `case_pack.py`:

1. Dependabot `package-ecosystem: pip` on `skillgate-ai`.
2. Pin `skillgate-ai==X.Y.Z` (lockfile). No unbounded `>=`.
3. Hosted modules keep importing `skillgate_ai.case_pack` **from the wheel**.
4. Private `engine` / Jev wrapper injects the Judge implementation.
5. Private CI `consume` job installs the pin; keep Vitest/`web.py` tests there.

Until the first public tag, private stays on in-tree code.

---

## 10. Ordered Phase 2 implementation checklist

Do these in order. Each item is a PR (or a tightly stacked pair) on **this** repo unless marked private.

1. **[this repo]** Enable secret scanning + push protection while still private.
2. **[this repo]** Add extract script `scripts/extract-from-skillgate-ai.sh` that copies **only** the allowlist (§4) from a local checkout path + SHA; refuse if deny-list paths appear in the destination.
3. Copy allowlisted `src/skillgate_ai/*.py` (except deny-list), `LICENSE`, rewrite `pyproject.toml` (§5), `.gitignore`.
4. AST `test_oss_surface.py` — must fail until strips land; keep it failing-closed.
5. Strip `config.py` vault/`db-creds`; strip `cli.py` `serve` + `store`; add `check`; add `judge.py` (`SkipJudge`) and `history.py`.
6. Strip `engine.py` Jev + `sandbox_queue_poller`; det-only live verdict = scorer AND.
7. Strip `harness.py` remote_harness; demo remains default when no key.
8. Strip `deploy.py` git-publish; optional `skillgate deploy`.
9. Replace `observability.py` with no-op stubs **or** lazy optional extra.
10. Copy pdf twins; migrate `evals/pdf.yaml` + `evals/pdf-sabotaged.yaml` into pack-local `evals/cases.yaml`; generate or commit fixtures; `evals/history/.gitkeep`.
11. Copy allowlisted tests; delete hosted tests if they slipped through; `pytest` green.
12. **Docker (foundations + build-strategies):** `.dockerignore` first, then `Dockerfile` multi-stage non-root `ENTRYPOINT skillgate` `CMD ["check","/pack"]`, then `compose.yaml`. Verify §7.5. **Do not copy private `Dockerfile` / `Dockerfile.vercel`.**
13. Public CI: `test` + `gate` + `docker` + `oss-surface`. Det only.
14. `docs/quickstart.md` + rewrite README (10 minutes, `pip install skillgate-ai`, Docker, copy-paste Action). Stripped `.env.example`.
15. Scan tree + `git log -p` for secrets. First tag `v0.3.0` (or chosen SemVer). Trusted Publishing + GHCR. Flip GHCR package public. Flip **this GitHub repo** public.
16. **[private skillgate-ai]** Dependabot pin to the published wheel; remove in-tree copies of schema/`check` as they are replaced.
17. **Later:** Marketplace `action.yml`; BYO HTTP judge; local OpenAI-compatible endpoint; optional extra example skills.

---

## 11. Risks (extract-specific)

| Risk | Mitigation |
| --- | --- |
| Copying `store.py` “for Mini history” | Violates pack-local SoR. Use `history.py` JSONL only. |
| Leaving `serve` in the CLI / Docker CMD | First-milestone fail. Tests assert no `serve` in public `cli.py` / Dockerfile. |
| `pip install skillgate` hitting the **other** PyPI project | Docs always `skillgate-ai`. CLI entry point can still be the `skillgate` **command**. |
| `config.py` still importing `vault` | OSS surface AST test. |
| `engine.py` fail-closed without Gateway | Default `SkipJudge`; det fixtures unlimited. |
| filter-repo of private history | Forbidden. Allowlist + new commits only. |
| GHCR stays private | Checklist item on the release PR. |
| History JSONL vs `:ro` pack mount | Document skip-on-EACCES; compose uses rw. |
| Schema drift vs private app | Schema lives only in this package after extract; private pins the wheel. |

---

## 12. This PR

Docs only:

- `docs/plans/2026-10-03-skillgate-oss-extract.md` (this file)
- `README.md` pointer at the plan

No application code, no Dockerfile yet, no visibility change, no copy from `skillgate-ai` except what was **read** to write the allowlist.
