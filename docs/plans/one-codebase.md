# One codebase — Skill Gate open-core plan

> **This document is Phase 1 (plan only) for `vigneshm1995personal/skillgate`.** Do **not** move the React app, add FastAPI, or change product code in this PR. Do **not** flip this repo public. Do **not** copy hosted secrets.

**Approved direction (Vignesh, 10 Oct 2026):** one public codebase following industry open-core practice — Sentry-style public core + thin private wrapper, Supabase-style `mode: local | cloud` switch, GitLab lesson against split repos, CI-enforced one-way imports.

**Inspected trees (read-only):**

| Repo | SHA | Note |
| --- | --- | --- |
| Public `vigneshm1995personal/skillgate` | `a504153` (`docs: pin skillgate-ai==0.4.0 in OpenAI judge guide`) | Private today; public later. PyPI **`skillgate-ai` 0.4.0**. |
| Hosted `vigneshm1995personal/skillgate-ai` | `1f482ee` (`fix: collapse leftover assistant splices on old runs`) | Private forever. In-tree package still **0.2.0** — does **not** yet pin the public wheel. |

Parent research: attached *Open-core code structure: research for Skill Gate (Oct 10, 2026)*. Earlier extract plan [`docs/plans/2026-10-03-skillgate-oss-extract.md`](2026-10-03-skillgate-oss-extract.md) and vanilla-JS UI plan [`docs/plans/2026-10-04-local-ui-setup-wizard.md`](2026-10-04-local-ui-setup-wizard.md) stay historical. **This plan supersedes the “never FastAPI / never `web/`” lock** for the UI path only. The hosted deny-list (auth, vault, Neon, Jev, Vercel Sandbox) still holds.

---

## For Vignesh (plain English)

- One product, one UI. The React app you already use on the hosted site becomes the only screen. The vanilla local UI goes away after that ships.
- `pip install skillgate-ai` then `skillgate ui` opens that same app on your machine. No Skill Gate account. One skill folder on disk plus `skillgate check` still exits 0 or 1.
- Local flow: connect Cursor / Codex / Claude → import skills from `~/.cursor/skills`, `~/.codex/skills`, `~/.claude/skills` (and project folders) → pick a skill → read the skill file → add dataset/checks → **you press Run** (never auto-run) → same results (drawn Passed/Failed, Result | Check | What happened, five answers) → Deploy back into those folders.
- API keys live in Settings. Not a blocking first-run wizard.
- Sign-in, billing, shared history, the hosted judge, cloud sandboxes, and try-out limits are **hidden** in local mode — not shown locked. They plug in later when the hosted app is in `cloud` mode.
- The private repo (rename to `skillgate-cloud` later) only adds accounts, Neon, billing, hosted judge, sandbox, and Vercel config. It pins `skillgate-ai` from PyPI. It does not keep a second copy of the screens.
- Core never imports cloud code. CI fails if it does. A FOSS-only job proves the public package still works with no account.
- License stays **Apache-2.0** on the public repo (already on PyPI). The private wrapper stays private.
- We move in five shippable steps. After each step both the local CLI/UI and the hosted site still work.
- Customer copy stays ordinary words: skill, check, run, passed, failed. No “SIWV”, “Jev”, “SoR”, “Hobby Function”, or “Mini”.
- This PR is the plan only. No product code yet.

---

## 0. Locked product rules

1. If a feature cannot work as **one pack on disk** plus `skillgate check` exiting **0 or 1** with **no Skill Gate account**, it is cloud and must not become the only path.
2. Deterministic fixture checks need **no API key**.
3. Local Run is **explicit**. Opening a skill, importing skills, or loading a dataset must not start a check.
4. Cloud-only chrome is **hidden** in `mode=local`, not shown as locked/paywalled.
5. Core never imports cloud. Cloud may import core (pinned wheel).
6. Docker image on this repo stays a CLI gate (`ENTRYPOINT skillgate`, `CMD ["check","/pack"]`). `skillgate ui` is a host process, not the image default.
7. Python stays `>=3.11` (current). Do not bump the floor in this migration.
8. `pip install skillgate` is a **different** PyPI project. Docs and install strings stay `skillgate-ai`.
9. Do not flip this GitHub repo public until Phase 5. Never flip `skillgate-ai` / `skillgate-cloud` public.
10. Customer-facing strings: no internal lingo.

---

## 1. What exists today (facts)

### 1.1 Public package (`skillgate`, PyPI `skillgate-ai` 0.4.0)

| Surface | Fact |
| --- | --- |
| CLI | `version`, `ingest`, `check`, `run`, `deploy`, `list`, `ui`. **No `serve`.** |
| Check | `skillgate check <pack>` → exit 0 green / 1 red / 2 live-without-key. `--expect-fail` inverts 0/1. |
| Engine | `gate.run_check` → harness + `engine.run_eval` + pack `evals/history/*.jsonl`. |
| Judges | `SkipJudge` (built-in checker) and OpenAI (`OPENAI_API_KEY`, Decisions API). Shared five-cell bank in `judge_bank.py`. |
| Harness | Local: demo, Cursor Agent CLI, Codex CLI, BYO HTTP. Sandbox: tempdir or optional Docker. |
| Deploy | Copy pack into `~/.cursor/skills/<name>/`, `~/.codex/skills/<name>/`, `~/.claude/skills/<name>/`. |
| Local UI | Stdlib HTTP on `127.0.0.1:8765`. Vanilla `index.html` / `app.js` / `app.css`. First-run **setup wizard**. Pack list is `--root/skills` only — **does not import** agent skill dirs. |
| Deps | typer, rich, pyyaml, pydantic, httpx, python-dotenv, pypdf, reportlab. **No FastAPI, no React.** |
| CI | `test`, `gate` (pdf 0 / sabotaged 1), `oss-surface` AST deny-list, `docker` CLI image. |
| Deny-list | `tests/test_oss_surface.py` forbids `auth_siwv`, `vault`, `store*`, `web`, `jev_qa`, `author`, `wizard`, `stage_b`, `deploy_git`, `remote_harness`. |

### 1.2 Hosted app (`skillgate-ai`, in-tree 0.2.0)

Still a **full copy** of engine + UI + cloud, not a wrapper. `pyproject.toml` still vendors FastAPI, uvicorn, jinja2, psycopg, cryptography, sentry-sdk. Dockerfile.vercel builds `web/` then `skillgate-ai serve --host 0.0.0.0`.

React app: Vite, React 19, shadcn/Tailwind, Vitest. Served from `web/dist` by FastAPI (`src/skillgate_ai/web.py`, ~3,300 lines).

**Nav stages (client, not URL routes):** `home` · `repository` (Skills) · `eval` (Evaluate: Skill / Checks / Gate tabs) · `deploy` · `history` · `settings`. Plus pre-auth **Landing** and **Login**.

**Auto-run today:** Evaluate auto-**seeds checks** when you open Checks. It does **not** auto-start a live eval. Local vanilla UI also waits for Run. Target lock: keep that — never auto-run.

**Hosted does not yet pin `skillgate-ai==0.4.0`.** Phase 2 is the first consume-from-wheel step.

---

## 2. Inventory — hosted screens / routes / APIs

Legend: **core** = public package; **cloud** = private wrapper via a slot; **drop** = do not bring forward (or fold into a core feature without a separate screen).

### 2.1 Screens / client stages

| Screen | File(s) | Verdict | Why |
| --- | --- | --- | --- |
| Marketing landing + Get started | `web/src/components/marketing/landing-page.tsx` | **cloud slot** | Sign-in CTA. Hidden in local. Cloud may keep it as the unauthenticated shell. Footer currently links the **private** GitHub repo — fix on public flip. |
| Login / allowlist error | `web/src/components/auth/login-page.tsx` | **cloud slot** | SIWV only. |
| Auth gate wrapper | `App.tsx` `AuthGate` | **cloud slot** | Local: skip; go straight to the app. |
| Home analytics | `home-page.tsx` | **cloud** (shared totals) / **drop as a required local home** | Neon rollup of runs/cost. Local home **is the Skills list**, not a SaaS dashboard. |
| Skills list (Repository) | `repository-page.tsx` | **core** | Local: imported agent dirs + project packs. Cloud: same UI, hosted catalog. |
| Skill detail | `skill-detail-page.tsx` | **core** | SKILL.md, pack browser, dataset, last run. Strip Neon-only mosaic/version tables into optional slots. |
| Evaluate — Skill tab | `eval-page.tsx` | **core**, reshape | Paste/zip stay. Local primary intake is **import from agent folders**, not “paste SKILL.md first”. |
| Evaluate — Checks tab | `eval-page.tsx`, `check-list.tsx` | **core** | Add/edit dataset. **Generate checks** (model assist) is a **cloud slot** (needs Gateway). Manual add + pack dataset stay core. |
| Evaluate — Gate / results | `gate-page.tsx`, `eval-result-mark.tsx`, `eval-result-shell.tsx`, `checks-results-table.tsx` | **core** | Drawn mark, Result \| Check \| What happened, five answers. Same view local and cloud. |
| Deploy | `deploy-page.tsx` | **core** (local copy) + **cloud slot** (git publish) | Local: Cursor / Codex / Claude folders. Git publish stays private. |
| History page + sheet | `history-page.tsx`, `history-sheet.tsx` | **core** pack-local; **cloud** shared/user history | Local reads `evals/history/*.jsonl`. Cloud Neon timeline is the slot. |
| Settings | `settings-page.tsx` | **core** (BYO keys) + **cloud slot** (vault/account) | Local writes `.env`. Not a wizard. Cloud encrypts per user in Neon. |
| QA “sign-in is off” banner | `App.tsx` | **cloud** | Never in the public UI. |
| Suggest skill updates | `skill-update-checklist.tsx` | **cloud slot** | Gateway-backed. Hidden locally. |
| Promote to check | `promote-check-dialog.tsx` | **core** | Writes the local pack. |
| Dataset viewer / pack browser | `dataset-viewer.tsx`, `skill-pack-browser.tsx` | **core** | |
| Run config / fixture bind | `run-config-accordion.tsx`, `fixture-bind-accordion.tsx` | **core** | Harness picker; cloud may add hosted-only harness ids via the harness interface. |
| Eval mosaic (GitHub-style year grid) | `eval-mosaic.tsx` | **cloud** | Needs long shared history. |
| Vanilla OSS wizard / picker | `src/skillgate_ai/local_ui/static/*` | **drop after Phase 1 cutover** | Keep until React local mode is proven, then delete. |

### 2.2 Hosted HTTP API (`web.py`)

| Method | Path | Verdict |
| --- | --- | --- |
| GET | `/api/auth/authorize` | **cloud** |
| GET | `/api/auth/callback` | **cloud** |
| POST | `/api/auth/signout` | **cloud** |
| GET | `/api/auth/me` | **cloud slot** — local returns `{auth_required: false, user: null}` |
| GET/PUT/DELETE | `/api/settings/keys` | **core** with storage adapter (local `.env` vs cloud vault) |
| GET | `/` `/assets/*` `/landing/*` icons | **core** SPA static (landing assets unused in local) |
| GET | `/api/status` | **core** + cloud fields behind mode (`auth_required`, `siwv_configured`, sandbox provider) |
| GET | `/api/debug/sentry` | **drop from public** (keep private if needed) |
| GET | `/api/skills` | **core** — local discovers agent + project dirs |
| GET | `/api/skills/{name}` | **core** |
| GET | `/api/skills/{name}/pack-file` `/pack-raw` | **core** |
| POST | `/api/skills/pack-file` `/pack-upload` `/paste` `/upload` | **core** |
| POST | `/api/evals/generate` | **core** for pack/heuristic seed; **cloud slot** for model assist |
| POST | `/api/evals/promote-draft` `/fixture-bind` `/pin` | **core** |
| GET | `/api/evals/dataset` | **core** |
| POST | `/api/evals/suggest-skill-updates` | **cloud** |
| POST | `/api/evals/baseline` | **core optional** (pack-local pin) / **cloud** if Neon SoR |
| POST | `/api/runs` | **core** — local calls `gate.run_check`; never auto-start from GET |
| GET | `/api/runs/{id}` POST skip/kill | **core** |
| GET | `/api/history` `/api/analytics` | **core** (local JSONL / empty analytics) + **cloud** Neon |
| POST | `/api/deploy` | **core** `mode=local`; **cloud** `mode=git` |
| — | tryout flag on `/api/runs` | **cloud slot** (caps). Local may still run one check; it must not be a hosted quota. |

### 2.3 OSS local HTTP API (today)

`GET /api/meta`, `GET/POST /api/packs`, `GET /api/pack`, `PUT /api/pack/skill-md`, `PUT /api/pack/cases`, `POST /api/pack/scaffold|fixtures|apply-advice`, `PUT /api/env`, `POST /api/check`, `GET /api/runs/{id}`, `POST .../kill`.

Phase 1 **replaces this surface** with the React app’s `/api/*` contract, implemented by a core Python API, with cloud routes unregistered in `mode=local`. Do not keep two JSON shapes.

### 2.4 Hosted Python modules

| Path | Verdict |
| --- | --- |
| `engine.py`, `harness.py`, `sandbox.py`, `scorers.py`, `case_pack.py`, `pack.py`, `ingest.py`, `fixture_bind.py`, `advice.py`, `report.py`, `live.py`, `eval_config.py`, `deploy.py` (local adapters) | **core** (already in public; hosted copy deleted in Phase 2) |
| `judge.py` / `judge_openai.py` / `judge_bank.py` | **core** (public already has these) |
| `jev_qa.py` | **cloud** — implements the Judge protocol |
| `auth_siwv.py` | **cloud** |
| `vault.py` | **cloud** |
| `store.py` / `store_postgres.py` | **cloud adapter** — see §3.1. Do not make Neon the OSS SoR. |
| `remote_harness/**` | **cloud** (Vercel Sandbox, Cursor Cloud, Codex remote, staging, poller) |
| `eval_slice.py` | **cloud** (Vercel Hobby maxDuration chunks) |
| `web.py` + `src/skillgate_ai/web/` | Split: core API + static in public; cloud routes in wrapper |
| `author.py`, `wizard.py`, `stage_b.py`, `suggest_skill.py` | **cloud** (model-authored drafts) |
| `deploy_git.py` | **cloud** |
| `catalog.py` | **core** after it also scans agent skill dirs |
| `regression.py`, `model_catalog.py` | **core** if they have no hosted imports; else strip and revisit |
| `observability.py` | **core stub**; real Sentry DSN only in cloud |
| `scripts/warm-sandbox-snapshot.py`, `vcr-prune-images.py`, `finalize-orphan-run.py` | **cloud** |
| `Dockerfile.vercel` | **cloud** |
| Hosted `Dockerfile` (`CMD serve`) | **cloud** — do not copy onto OSS CLI image |

---

## 3. Interfaces (stable seams)

Cloud implements these. Core depends on **protocols + defaults**, never on cloud modules.

### 3.1 Storage

```
Storage
  load_skill / save_skill / list_skills
  load_dataset / save_dataset          # evals/cases.yaml in the pack
  append_run / list_runs               # history
  save_settings / load_settings        # keys presence, never echo secrets
```

| Mode | Implementation |
| --- | --- |
| **local** | Pack on disk. History = `<pack>/evals/history/*.jsonl` (already in OSS). Settings = workspace `.env` (already `PUT /api/env`). Optional later: a local SQLite **cache** for the Skills list — not required for Phase 1. |
| **cloud** | Neon (`store_postgres.py` today: `skill_versions`, `eval_runs`, `deploy_attempts`, `eval_baselines`, `user_secrets`). Pack files still live on disk in the Function image / sandbox inject. Vault ciphertext stays cloud. |

**Do not** ship `store.py` as the OSS source of truth. Pack JSONL remains the no-account SoR. Cloud may *also* record runs in Neon.

### 3.2 Harness (who runs the skill)

```
Harness.run(sandbox, prompt, skills, timeout) -> HarnessResult
Sandbox.run(command, env, timeout) -> process result
```

| Mode | Implementation |
| --- | --- |
| **local** | Existing: DemoHarness, CursorAgentHarness (`agent` / `cursor-agent`), CodexCliHarness (`codex exec`), BYO HTTP. Sandbox: tempdir default, optional Docker. |
| **cloud** | `remote_harness/` — Vercel Sandbox microVM (product lock when `VERCEL=1`), Codex Agents API, Cursor Cloud, staging inject, queue poller, eval-slice resume. |

Core `resolve_harness` stays local-only. Cloud wraps or replaces the resolver **outside** the package (inject at process boot). Core must not `import remote_harness`.

### 3.3 Judge (who scores a finished check)

Public already has the seam:

```
Judge.judge(goal, artifacts, transcript_tail) -> {passed, cells, answers, ...}
```

Five questions (customer labels): Got the job done? Got it right? Followed the rules? Used the right evidence/actions? Delivered a good result?

| Mode | Implementation |
| --- | --- |
| **local** | Skip (built-in checker) or OpenAI with **the user’s** `OPENAI_API_KEY`. |
| **cloud** | Hosted Jev (`POST https://ai-gateway.vercel.sh/v1/evaluate`, model `typesafe-ai/jev`) plus server Gateway key. Same five-cell bank (`judge_bank.py` must stay the single ordinal source). |

Results UI always renders the same table. If the judge skipped, show the built-in checker copy — not an empty “locked” panel.

### 3.4 Auth

```
Auth
  required: bool
  current_user() -> None | {id, email, name}
  login_url / logout
```

| Mode | Implementation |
| --- | --- |
| **local** | `required=false`. No cookies. No landing interstitial. |
| **cloud** | Sign in with Vercel (`auth_siwv.py`), httpOnly cookies, allowlist / owner email, QA-only `SKILLGATE_AUTH_OPEN`. |

Settings keys: local `.env`; cloud Fernet vault keyed by `siwv:<sub>` (or `qa-open` / `mini-open` on those envs — those identities never ship in public docs as a how-to).

### 3.5 UI mode + slots

```
mode: local | cloud          # env SKILLGATE_MODE, or inferred: VERCEL=1 → cloud
slots: {
  signIn, billing, sharedHistory, hostedJudge, sandboxes, tryoutCaps,
  generateChecks, gitPublish, suggestUpdates, analyticsHome
}
```

Like Supabase `NEXT_PUBLIC_IS_PLATFORM`: one React tree. Slot components are empty in local. Cloud registers implementations at boot (plugin map or `window.__SKILLGATE_SLOTS__` / `/api/status.slots`). **Hidden, not locked.**

---

## 4. What must stay private

### 4.1 Secrets, billing, infra (never in the public tree)

- SIWV: `VERCEL_APP_CLIENT_ID` / `SECRET`, `SKILLGATE_SIWV_ALLOWLIST`, `SKILLGATE_OWNER_EMAIL`, `SKILLGATE_AUTH_OPEN`
- Vault: `SKILLGATE_SECRETS_KEY`, `user_secrets` ciphertext
- Neon: `DATABASE_URL` / `POSTGRES_*`, `db-creds.env`
- Vercel Sandbox: `VERCEL_TOKEN` / `VERCEL_OIDC_TOKEN`, project/team ids
- Git publish / staging: `SKILLGATE_SKILLS_GITHUB_TOKEN`, staging repo tokens
- Production `SENTRY_DSN`
- Hosted Gateway key used as **Skill Gate’s** Jev/judge key (user BYO keys in `.env.example` are fine)
- Billing provider keys (not in tree today — see open decisions)
- QA bypass semantics as a copy-paste runbook

### 4.2 Hosted code that is unsafe or unwise to make public

| Item | Why |
| --- | --- |
| `auth_siwv.py` allowlist/QA-open control flow | Easy to mis-copy; skip-auth is a production footgun |
| `vault.py` | Crypto + secret layout |
| `store_postgres.py` + Mini `store.py` as SoR | Ties OSS to Neon/SQLite and hosted history |
| `remote_harness/vercel_sandbox.py` + poller + eval_slice | Infra, tokens, Hobby workarounds |
| `jev_qa.py` | Hosted judge endpoint + fail-closed policy; keep as cloud Judge impl |
| `deploy_git.py` | PAT push path |
| `scripts/warm-sandbox-snapshot.py` and friends | Ops |
| Dockerfile.vercel / hosted `CMD serve` | Would revive “the image is a web server” |
| Landing “Open source on GitHub” pointing at the **private** repo | Wrong until Phase 5, and it should point at `skillgate` not `skillgate-ai` |

**Safe to make public (and should):** React dashboard chrome, results table, five-cell labels, pack browser, local deploy adapters, engine, OpenAI judge, CLI, seed pdf twins.

---

## 5. Licensing

**Recommendation: keep Apache-2.0 on the public repo.**

| Option | Fit |
| --- | --- |
| **Apache-2.0 (chosen)** | Already on PyPI 0.4.0 and in `LICENSE`. Patent grant. Matches Supabase/Prefect/Dagster-style Apache cores. No relicensing churn. |
| MIT | Also fine for a Sentry-like wrapper, but switching now is busywork. |
| AGPL / fair-code / FSL | Wrong for “engine + UI everyone runs locally.” Would scare the CLI/CI audience. |
| `ee/` inside the public repo | Not needed until you sell **self-hosted** extras (SSO, audit log). Then add `ee/` + a key, Langfuse-style — do not start a third repo. |

Private wrapper: no public license. After rename, `skillgate-cloud` stays private.

CLA / DCO: decide at Phase 5 with `CONTRIBUTING.md`. Default: incoming PRs are Apache-2.0 (Apache §5).

---

## 6. Target local UX (acceptance)

`skillgate ui` (`mode=local`):

1. **Connect** Cursor / Codex / Claude — import skills from `~/.cursor/skills`, `~/.codex/skills`, `~/.claude/skills`, plus project `skills/` (and `--root`). Deduplicate by folder name; show source (“Cursor”, “this project”).
2. **Skills list** is the home screen. No wizard. No account.
3. **Pick a skill** → read SKILL.md → add dataset/checks (manual + pack files). **Run is a button.** Opening the page does not start a check. Seeding/generating checks is not a run.
4. **Results** match hosted: Checking → drawn Passed/Failed mark; table columns Result \| Check \| What happened; expand for the five answers (or built-in checker copy). **Deploy** copies into those same agent folders.
5. **Settings** for keys (OpenAI, Cursor, Codex, Anthropic). Optional. Built-in checker if skipped.

Still true with no UI: one pack on disk, `skillgate check`, exit 0/1, no account.

---

## 7. Phased migration

Every phase **ships**. After each phase: OSS `check` 0/1 still works; hosted site still serves. No “dark season” rewrite.

Effort labels are **estimates** (relative size of the change set, not a calendar). S = few files / one PR; M = one subsystem; L = several subsystems that must land together; XL = multi-PR series.

### Phase 1 — React UI in core, `mode` switch, serve locally

**Estimate: L** (copy `web/`, wire a core API, dual-serve until cutover).

Public repo:

- Copy hosted `web/` (allowlist: `web/src`, `web/package.json`, lockfile, Vite/Vitest config, `components.json`). Strip landing screenshots only if they leak private URLs; brand assets that are already on the hosted site are fine.
- Add `SKILLGATE_MODE` (`local` default in this package). `/api/status` (or `/api/meta`) returns `{mode, slots}`.
- Implement the React API contract in core Python. Prefer **one** server (FastAPI is acceptable here — this plan **explicitly supersedes** the old “no FastAPI in the wheel” rule). `skillgate ui` serves `web/dist` on loopback **8765**.
- Local adapters: disk catalog including agent skill dirs; `.env` settings; `gate.run_check` for POST `/api/runs`; JSONL history; local deploy.
- Hide cloud slots. No AuthGate. Home = Skills list. Settings = keys, not vault copy.
- **Do not auto-run.** Remove or gate hosted “Start Evaluations” live-only hard-fail so local can use the built-in checker.
- Wheel: build `web/` in CI/release, ship `web/dist` as package data. Dev: `pnpm --dir web build` then `pip install -e .`.
- Keep vanilla `local_ui` until a follow-up PR in this phase deletes it after live QA.
- Relax `test_oss_surface` only as needed (`web/` frontend allowed; still deny `auth_siwv`, `vault`, `jev_qa`, `remote_harness`, `store_postgres`). FastAPI may appear in required or `[ui]` extra — pick in open decisions; default **required** so `pip install skillgate-ai && skillgate ui` works.

Hosted:

- **Freeze new UI work** on `skillgate-ai/web` except production fixes. Point contributors at the public `web/`.
- Keep serving **its** `web/dist` so QA/prod do not wait on a PyPI bump.
- Do not rename the repo yet.

Both apps work: hosted unchanged at runtime; OSS gains React `skillgate ui`; CLI Docker unchanged.

### Phase 2 — Unify check / judge logic; delete hosted copies

**Estimate: L** (pin wheel, delete duplicate Python, inject Jev).

- Hosted `pyproject.toml` pins `skillgate-ai==X.Y.Z` (the Phase 1+ release). No unbounded `>=`.
- Delete hosted in-tree duplicates of `engine`, `harness` (local), `sandbox` (local), `scorers`, `case_pack`, `judge_bank`, `report`, `gate`, etc.
- Hosted injects: Jev Judge, remote harness resolver, Neon storage, SIWV, vault, eval_slice, git deploy.
- One `run_eval` / one five-cell bank. Hosted tests that imported in-tree modules now import the wheel.
- Public `check` exit codes unchanged.

Both apps work: hosted CI installs the pin; a mismatch is a failed consume job, not a silent fork.

### Phase 3 — Hosted becomes a thin wrapper; rename

**Estimate: M–L** (delete remaining product screens from the private tree).

- Private app: auth, Neon adapter, billing slot, hosted judge, sandbox harness, Vercel/Docker.serve config, slot registration.
- UI and core API come **from the wheel**. No copied `EvalPage`.
- Rename repo `skillgate-ai` → `skillgate-cloud` when the wrapper is actually thin (not before — the current tree is still the product).
- Hosted `skillgate-ai serve` becomes a cloud entrypoint (`SKILLGATE_MODE=cloud`).

Both apps work: same React, different mode and adapters.

### Phase 4 — CI guards

**Estimate: M** (workflows + bot).

Public:

- Keep/extend AST **import-boundary** (core never imports cloud module names).
- **FOSS-only** job: install the wheel with no cloud extra, `pytest`, `skillgate check` pdf twins, `skillgate ui` API `mode=local` + `auth_required=false`.
- UI job: `pnpm test` + `pnpm build`.
- Release: Node build then `python -m build` so the wheel contains `web/dist`.

Private:

- Consume job: `pip install skillgate-ai==pin`, boot `mode=cloud`, run hosted e2e against the pin.
- Bot (Renovate/Dependabot) opens a pin-bump PR; cloud e2e must pass before merge.

### Phase 5 — Public flip

**Estimate: S–M** (process + docs, not architecture).

- Secret scan of git history (gitleaks/trufflehog) — this repo was allowlist-extracted, but scan again after `web/` lands.
- `CONTRIBUTING.md`, public README (10-minute no-account path + `skillgate ui`), license line remaining Apache-2.0.
- Flip **this** GitHub repo public. Flip GHCR package if still private. **Never** flip `skillgate-cloud`.
- Landing/docs GitHub links point at `vigneshm1995personal/skillgate`.
- Optional later: `posthog-foss`-style mirror that is this repo (already OSS-only).

---

## 8. Test plan + live QA / recording (per phase)

### Shared invariants (every phase)

- `skillgate check skills/pdf` exit 0; `skills/pdf-sabotaged` exit 1; `--expect-fail` inverts.
- No account. Blank BYO keys → built-in checker.
- Docker image still CLI (Phase 1+ tests already in `tests/test_dockerfile.py`).
- Customer copy: grep UI strings for `SIWV`, `Jev`, `SoR`, `Hobby`, `Mini`, `eval_slice` — fail if they appear in user-visible React.

### Phase 1

**Automated**

- Vitest: results table, five-cell order, `mode=local` hides sign-in/billing/history-cloud/hosted-judge chrome.
- Pytest: POST `/api/runs` does not start on GET/pack load; import lists `~/.cursor/skills` fixtures; Settings writes `.env`; deploy still copies to a temp skills root.
- Playwright or stdlib HTTP: open skill → idle → click Run → poll until drawn mark + Result/Check/What happened.

**Live QA / recording** (screen recording, ~3 min, no secrets)

1. Fresh venv, `pip install -e .`, `skillgate ui --open`.
2. Skills list shows project pdf twins; Connect/import from a temp `~/.cursor/skills` copy.
3. Open pdf-sabotaged, show SKILL.md, do **not** see a run start.
4. Press Run (built-in checker) → Failed mark + table + expand a row.
5. Settings: paste a dummy key field, save, confirm no wizard.
6. Deploy pdf (green) into the temp Cursor skills dir; `test -f .../SKILL.md`.
7. `skillgate check` on the same pack still 0/1 in a terminal.

Keep the recording under `docs/proof/` only if it contains no keys and no private hostnames.

### Phase 2

**Automated:** hosted test suite on the pin; public `test_oss_surface` still denies `jev_qa`; a cloud-only test proves Jev injects without core importing it.

**Live QA:** production/QA hosted run of pdf (Codex or Cursor) still draws the same mark/table; OSS OpenAI judge still scores with a user key.

### Phase 3

**Automated:** private repo file count — no `web/src/components/dashboard/eval-page.tsx`; wrapper imports `skillgate_ai` only.

**Live QA:** deploy hosted to QA; sign-in still works; local `skillgate ui` still has no sign-in.

### Phase 4

**Automated:** a CI fixture that `import skillgate_ai.cloud` (or similar) from `src/skillgate_ai` fails; FOSS job has no `DATABASE_URL`; Dependabot PR runs cloud e2e.

**Live QA:** merge a no-op pin bump on the wrapper.

### Phase 5

**Automated:** gitleaks clean; README does not say `pip install skillgate`.

**Live QA:** anonymous browser, public repo, `pip install skillgate-ai` from PyPI, `skillgate ui`, 10-minute red→green pdf path.

---

## 9. Open decisions

1. **FastAPI in the default wheel vs `[ui]` extra.** Default recommendation: required dep so `pip install skillgate-ai && skillgate ui` works. Alternative: `pip install skillgate-ai[ui]` keeps the CLI wheel smaller.
2. **How cloud registers slots** — Python entry points vs `/api/status.slots` vs a tiny `skillgate_cloud` JS bundle the wrapper injects. Recommendation: `/api/status.slots` + React conditionals first (simplest, one UI bundle).
3. **Billing** — not in the hosted tree today. Treat as a reserved slot. Provider (Stripe, Lemon Squeezy, Vercel Marketplace) is undecided; do not invent UI copy until it is.
4. **Try-out caps** — hosted has a `tryout` flag (single check, not Deploy SoR). Rate limits/caps are not clearly shipped. Local: unlimited built-in checker; live uses the user’s key. Caps are cloud-only when they exist.
5. **Local SQLite** — skip in Phase 1 (JSONL + files). Add only if the Skills list needs indexing.
6. **Generate checks** — keep as cloud slot (Gateway). Local: manual add + pack dataset + optional heuristic seed that needs no key.
7. **Port** — keep OSS **8765** for `skillgate ui`; hosted **8477** / `$PORT`. Do not EXPOSE in the CLI image.
8. **Vanilla UI deletion timing** — same Phase 1 series after recording, not the first PR that copies `web/`.
9. **Repo rename timing** — after Phase 3, not now (hosted is still the fat app).
10. **Node version** — hosted Dockerfile.vercel uses Node 22; match that in public CI.
11. **Home screen in cloud** — keep analytics Home as a cloud slot, or make Skills the home in both modes. Recommendation: Skills is home in both; analytics is a cloud nav item.
12. **Import of agent dirs on first launch** — scan automatically vs an explicit “Connect” button. Recommendation: scan on start, with a Connect empty-state if none found (matches Vignesh’s flow without a wizard).
13. **`web.py` filename** — OSS deny-list currently forbids `web.py`. Use `skillgate_ai.api` / `skillgate_ai.server` in public; wrapper may keep a thin `serve`.
14. **Python 3.13** — out of scope; stay `>=3.11`.

---

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| Two UIs drift during Phase 1 | Freeze hosted `web/` except hotfixes; land React in public first. |
| FastAPI/uvicorn bloat the CLI wheel | Optional extra (decision 1) or accept the dep for one-command UI. |
| Copying `web.py` wholesale pulls SIWV/vault | Reimplement core routes; do not rsync `web.py`. |
| Hosted still on 0.2.0 in-tree | Phase 2 pin is mandatory before deleting duplicates. |
| `pip install skillgate` wrong package | Docs + README stay `skillgate-ai`. |
| Auto-run regresses | Tests: loading `/api/skills/{name}` does not create a run. |
| Docker starts serving UI | Existing Dockerfile tests; do not add `ports` to default compose. |
| Public flip leaks tokens from `web/` history | Allowlist copy as new commits (same as original extract); scan before Phase 5. |
| Judge ordinals drift | `judge_bank.py` is the only bank; hosted Jev imports it from the wheel. |
| GitLab-style split returns | CI import-boundary + “no dashboard TSX in the wrapper” check. |

---

## 11. This PR

Docs only:

- `docs/plans/one-codebase.md` (this file)
- README pointer under Docs

No application code, no `web/` copy, no FastAPI, no visibility change, no rename of the hosted repo.
