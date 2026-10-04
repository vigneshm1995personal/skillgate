# Local UI + setup wizard — Implementation Plan

> **This document is Phase 1 (plan only) for OSS `vigneshm1995personal/skillgate`.** Do **not** implement `skillgate ui`, HTTP routes, or Docker UI in this PR. Do **not** copy the private hosted dashboard. Do **not** flip this repo public.

**Goal:** Give a stranger a **local** front for the same CLI/engine they already have: pick or create one skill pack on disk, write `SKILL.md` + `evals/cases.yaml`, run `check`, see GREEN/RED rows, apply the sabotaged-description fix. Still **no Skill Gate account**, no Neon, no SIWV, no hosted Jev.

**Parent (locked):** [`docs/plans/2026-10-03-skillgate-oss-extract.md`](2026-10-03-skillgate-oss-extract.md). Decision rule unchanged: if a feature cannot work as **one pack on disk** plus `skillgate check` exiting **0 or 1** with **no account**, it does not belong here.

Inspected tree: `main` @ `a4bd241` (`chore: release workflow + publish checklist`). PyPI dist **`skillgate-ai` 0.3.0**. CLI command **`skillgate`**. Hosted app stays private at `vigneshm1995personal/skillgate-ai`.

---

## 0. What exists today (facts, not hunches)

| Surface | Fact |
| --- | --- |
| CLI commands | `version`, `ingest`, `check`, `run`, `deploy`, `list`. **No `serve`.** Tests: `tests/test_check_cli.py::test_no_serve_command`. |
| Check semantics | `skillgate check <pack>` → `typer.Exit(0 if report.passed else 1)`. `--expect-fail` inverts. `--live` without a key → exit **2** (`MissingLLMKeyError`). |
| Demo path | No BYOLLM key → `resolve_harness("auto")` returns `DemoHarness`. Token overlap on **description only** (folder name is not a keyword source — that is why `pdf-sabotaged` stays red). If triggered, runs `scripts/agent_entry.py` in a tempdir sandbox. Same scorers as live. |
| Red twin | `skills/pdf-sabotaged` meal-planner `description:` → 1/8 PASS (`no-trigger-unrelated`), 7 trigger misses. CLI prints `Corrected SKILL.md description` via `advice.advise_suite` + `_reference_twin` (looks for `skills/pdf`). Exit 1. |
| Green twin | `skills/pdf` → 8/8 GREEN, exit 0. |
| Ingest | `name` must match folder basename (`^[a-z0-9]+(?:-[a-z0-9]+)*$`, 1–64 chars), except Docker mount basename `pack`. Description required, ≤1024. |
| Pack SoR | `<pack>/evals/cases.yaml` schema `1`. `save_case_pack` / `load_case_pack` / `expand_from_pack` already exist. History JSONL under `<pack>/evals/history/`. |
| Report JSON | `report_to_dict` already has `gate` (`green`/`red`), `passed`, `tasks[].advice`, suite `advice.paste`. `--json` is CLI opt-in. |
| Engine | `run_eval(..., on_progress=..., control=RunControl)`. `live.py` is in-process skip/kill + stdout ring buffer. |
| Docker | `ENTRYPOINT ["skillgate"]`, `CMD ["check", "/pack"]`, no `EXPOSE`, no ports in `compose.yaml`. Tests fail if `serve` appears in the Dockerfile. |
| Deny-list | `tests/test_oss_surface.py` forbids files named `web.py` / `wizard.py` and imports of `skillgate_ai.web`, `.wizard`, `.auth_siwv`, `.vault`, `.store*`, `.jev_qa`, `.author`, `.stage_b`, `.deploy_git`, `.remote_harness`. `scripts/extract-from-skillgate-ai.sh` DENY array matches. |
| Deps | Required: typer, rich, pyyaml, pydantic, httpx, python-dotenv, pypdf, reportlab. **No FastAPI/uvicorn/jinja2.** Proof matrix item 14 treats that as a shipped invariant. |
| Hosted leftovers in OSS (do not revive as product) | `live.py` comments mention `GET /api/runs/{id}` and “Gate UI”. `eval_config.EvalConfigError` says “from the UI or CLI”. `harness.auto_live_harness_name` mentions “UI chrome”. `pack.browser_files` / `pack_preview` / `case_pack.dataset_view` are local pack APIs with no HTTP. `fixture_bind.py` docstring: “OSS has no Start-Evaluations UI. Wizard/regression stay in the private app.” |

**Hunch (label explicitly):** private `skillgate_ai.wizard` / `web.py` (~118 KB FastAPI + React `web/` SPA) is generated-check drafts + hosted dashboard. Do not open that tree for copy-paste. Rebuild a thin local shell on the APIs above.

---

## 1. Locked product constraints

1. OSS still works with **one pack on disk** + `skillgate check` exit **0 or 1** and **no account**. UI is optional sugar.
2. Deterministic fixture checks need **no API key**. Wizard BYO-key step is optional and must not block demo.
3. Do **not** add Skill Gate login, billing, shared history, Neon, SIWV, vault, Jev, or Vercel Sandbox.
4. Do **not** revive `skillgate serve`. New command is **`skillgate ui`**.
5. Do **not** change Docker `ENTRYPOINT`/`CMD`. The image remains a CLI gate, not a web server.
6. Do **not** name new modules `web.py` or `wizard.py`. Do not create `src/skillgate_ai/web/`.
7. Do **not** copy `web/`, `docs/brand/`, `docs/checks-ui-mock/`, or private Jinja templates.
8. Do **not** flip the GitHub repo public from this work.

---

## 2. How a stranger starts it

After `pip install skillgate-ai` or `pip install -e .`:

```bash
skillgate ui                          # http://127.0.0.1:8765
skillgate ui --pack skills/pdf-sabotaged
skillgate ui --root . --open
```

| Flag | Default | Notes |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Loopback only. `--host 0.0.0.0` is allowed but prints a warning: no auth, local process, not the hosted app. |
| `--port` | `8765` | **Not 8477** (private hosted `serve`). |
| `--root` | `paths.project_root()` | Workspace confine for browse/create. Writes must stay under this root unless the user pastes an absolute path they own (still no `..` traversal). |
| `--pack` | none | Skip picker; open that pack in the editor/check view. |
| `--open` | false | `webbrowser.open` the loopback URL. |
| `--no-browser` | — | Explicit no-open (if `--open` becomes default later, keep this). |

Help text must say: local process, no account, demo harness without keys, Docker `check /pack` is unchanged.

`skillgate serve` must still fail with “No such command”.

---

## 3. Stack (locked for Phase 2)

**Stdlib HTTP + vanilla HTML/CSS/JS inside the wheel. No FastAPI, no uvicorn, no React, no shadcn, no new required deps.**

| Piece | Choice | Why |
| --- | --- | --- |
| Server | `http.server.ThreadingHTTPServer` + a small `BaseHTTPRequestHandler` | Zero new deps; `pip install skillgate-ai` then `skillgate ui` works. Keeps proof-matrix “no FastAPI” true. |
| Pages | One HTML app + CSS/JS as package data | Wizard is 4 steps + a results table. Not a SPA rewrite of private `web/`. |
| Check progress | Poll `GET /api/runs/{id}` every ~400ms | `live.RunControl` + `engine.on_progress` already exist. Do not add SSE in v1. |
| JSON | `report_to_dict` / `progress_to_dict` | Same payload CLI `--json` uses. |
| Templates | None (static files + `json.dumps` APIs) | Avoid re-adding jinja2. |

**Rejected for v1**

- FastAPI `[ui]` extra — extra install friction; looks like hosted `serve`.
- Copying private React/shadcn — deny-list + “do not copy hosted app”.
- Subprocess `skillgate check` as the only engine — loses `on_progress` / skip-kill; harder to keep JSON identical. CLI and UI must call one Python function (see §5).

**setuptools:** add package data for the static files (private extract **deleted** `web/templates/*`; this is a **new** local path, not that tree):

```toml
[tool.setuptools.package-data]
skillgate_ai = ["local_ui/static/*"]
```

---

## 4. Screens / UX (routes are local, not hosted)

Browser origin is always `http://127.0.0.1:8765` (or the chosen loopback). No client-side routing library; hash or querystring is enough.

### Screen A — Pack picker (`/`)

- List skill folders under `--root/skills` (and `--root` itself if it is a pack).
- Text field: absolute or root-relative path → “Open”.
- Button: “Create a new pack”.
- Seed hint: `pdf` (green twin) and `pdf-sabotaged` (intentional red) when those dirs exist.
- Footer: “No account. Demo harness if no key in `.env`.”

### Screen B — Wizard (`/setup?pack=…` or `/setup` for create)

Four steps. Back/Next. Validate on Next. Never call a Skill Gate API.

**Step 1 — Folder**

- Create: parent directory (default `--root/skills`) + `name`.
- Create means `mkdir` then lock `name` = basename.
- Open existing: show basename; `name` field is read-only and must equal basename (Docker `/pack` exception is an advanced note, not a wizard default).
- Client + server validate `ingest.NAME_RE`. On mismatch, show the ingest hint verbatim: *Rename the folder or the `name` field so they match.*

**Step 2 — `SKILL.md` frontmatter**

- Fields: `name` (locked), `description` (textarea, required, live `description_is_usable` hint), optional `license`, `compatibility`, body markdown (textarea; default a short “When to use / How to work” stub).
- Save writes YAML frontmatter + body via a **new** helper `write_skill_md` (ingest is read-only today; `rewrite_skill_description` only patches `description:`).
- Do not generate checks from an LLM. `description_is_usable` is the only “author assist” in OSS.

**Step 3 — Evals + fixtures**

Radio:

1. **Use existing** `evals/cases.yaml` (show `dataset_view` table).
2. **Scaffold trigger-only demo** (default for brand-new packs): schema 1, `skill: <name>`, two **pinned** cases:
   - `should-trigger-1`: `should_trigger: true`, prompt uses keywords from the description, **no golden** (trigger-only — demo can go green without `scripts/agent_entry.py`).
   - `no-trigger-unrelated`: copy the pdf twin’s pytest/FastAPI prompt, `should_trigger: false`, `golden: null`.
3. **Clone pdf demo layout** (optional, only if `skills/pdf` is on disk): copy cases/fixtures/goldens/scripts into the new folder, rewrite `skill:` / `name:` to the new basename. Completeness path needs `agent_entry.py`; do not silently promise GREEN without scripts.

Fixture controls:

- List files under `evals/fixtures/` (`pack.list_pack_files`).
- “Point at a file” → `copy_into_pack`.
- “Synthesize sample” → `write_sample_fixture` (must surface `CannotSynthesizeFixture` for photo/scan).
- For pdf-shaped descriptions, button “Ensure demo PDFs” → `ensure_demo_pdfs` (same as CLI `_prepare_pack_fixtures`).

`save_case_pack` + `_validate_pack_on_disk` will error if a completion case references a missing fixture/golden — show `SuiteError.message` + `hint`.

**Phase 2 must also fix the existing `{orig}` NameError in `load_case_pack` / `save_case_pack` / `suite_from_pack` (uses `{orig}` where the except name is `exc`).** Wizard invalid-YAML would crash today. Tiny, same-PR as first UI write to `case_pack.py`.

**Step 4 — Optional BYO key**

- Checkbox default **off**: “Run with demo harness (no key)”.
- Optional `.env` editor for `CURSOR_API_KEY` / `CODEX_API_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `AI_GATEWAY_API_KEY` only (same names as `.env.example`).
- Write to `--root/.env` with `override=False` semantics for *other* keys: merge, do not wipe unrelated lines. Never POST keys anywhere. Never show this step as required.
- Live toggle on the check screen maps to `--live` (exit 2 / HTTP 409 if no key) vs default auto/demo.

**Finish** → Screen C.

### Screen C — Check results (`/pack?path=…`)

- Header: skill name, path, harness label (`config_label`), **GREEN or RED**, `passed_count/task_count`, **exit equivalent** (`0` / `1` / `2`) matching CLI.
- Table: one row per task — id, PASS/FAIL, first failure, expand for why/fix (`task.advice`).
- Suite-level advice panel when red: headline, why, change, **`advice.paste` in a `<pre>`**, `demo_note`.
- Buttons: **Run check** (default demo/auto), **Run live** (requires key), **Apply description fix** (calls `rewrite_skill_description` or `apply_description_fix` on this same folder — never switch to the green twin), **Re-run**.
- Dim banner when falling back to demo (same sentence CLI prints).
- Optional local history: `load_history(pack)` last N JSONL rows. Pack-local only.

### Intentional red path (must be a first-run tutorial, not a hidden easter egg)

On the picker, a card: **“See a red gate (no account)”**.

1. Open `skills/pdf-sabotaged` (or copy it into a temp folder so the repo copy stays sabotaged — prefer **opening the seed in place** and applying the fix only if the user clicks Apply; tests use `tmp_path` copies).
2. Run check → RED, 1/8, paste block whose description talks about PDFs and **must not** contain `grocery` / `dinner` (same assertion as `test_check_sabotaged_red`).
3. Apply paste → rewrite `description:` on **this** pack.
4. Re-run → GREEN (demo will now trigger; pdf-sabotaged **does** ship `scripts/agent_entry.py` + goldens, so completion can pass).
5. Copy: “CI still uses `skillgate check`; this UI called the same engine.”

If the user applies the fix to the committed seed, `tests/test_check_cli.py::test_check_sabotaged_red` would fail in a dirty worktree — wizard Apply in the **repo checkout** should confirm, or tests always copy to `tmp_path`. Prefer: UI can write the seed (user’s machine); CI tests never mutate `skills/pdf-sabotaged`.

---

## 5. Files to add / change (Phase 2)

### 5.1 New

| Path | Role |
| --- | --- |
| `src/skillgate_ai/gate.py` | **`run_check(pack, **opts) -> CheckResult`**. Move the body of `cli._run_gate` here (resolve pack, harness, `run_eval`, persist history, compute exit code including `--expect-fail` and live-missing-key). CLI and UI both call this. `CheckResult`: `report`, `exit_code`, `demo_notice: str \| None`, `error`. |
| `src/skillgate_ai/local_ui/__init__.py` | Package marker. |
| `src/skillgate_ai/local_ui/server.py` | Bind loopback, route table, JSON + static. |
| `src/skillgate_ai/local_ui/api.py` | Handlers: pack list/create, skill md read/write, cases load/save, fixture copy/synth, env optional write, start check, poll run, apply advice. No auth. |
| `src/skillgate_ai/local_ui/static/index.html` | Picker + wizard + results (can be one file with sections). |
| `src/skillgate_ai/local_ui/static/app.js` | Fetch JSON, poll runs, render rows. |
| `src/skillgate_ai/local_ui/static/app.css` | Minimal readable layout (system font, GREEN/RED tokens). Keep boring. |
| `src/skillgate_ai/skill_md.py` | `write_skill_md(folder, *, name, description, body, **optional)` + round-trip through `ingest_skill`. Used by wizard and tests. |
| `src/skillgate_ai/scaffold.py` | `create_pack(parent, name)`, `scaffold_trigger_cases(pack)`, optional `clone_pdf_layout`. No LLM. |
| `tests/test_gate.py` | `run_check` on pdf / pdf-sabotaged / expect-fail / live-without-key — same exits as CLI. |
| `tests/test_local_ui.py` | In-process HTTP against `local_ui.server` (stdlib `http.client` or `urllib`). See §7. |
| `tests/test_scaffold.py` | Name/folder rule; trigger-only pack checks green with no keys. |
| `docs/ui.md` | How to start `skillgate ui`; red path; Docker stays CLI. |

### 5.2 Change

| Path | Change |
| --- | --- |
| `src/skillgate_ai/cli.py` | Add `@app.command("ui")`. `_run_gate` becomes a thin wrapper around `gate.run_check`. **Do not** add `serve`. |
| `src/skillgate_ai/case_pack.py` | Replace `{orig}` with `{exc}` in three `SuiteError` raises. |
| `src/skillgate_ai/advice.py` | No logic change required; UI consumes `FixAdvice` via `report_to_dict`. Optional: reuse `apply_description_fix`. |
| `pyproject.toml` | `package-data` for `local_ui/static/*`. **Do not** add fastapi/uvicorn. Version bump is a **later** release decision (hunch: `0.4.0` when UI ships; this plan PR does not bump). |
| `README.md` / `docs/quickstart.md` | After `skillgate check` 10-minute path, add “optional local UI: `skillgate ui`”. Keep Docker section as `check /pack`. |
| `docs/pack.md` | One paragraph: wizard writes the same `evals/cases.yaml` schema 1. |
| `tests/test_check_cli.py` | Keep `test_no_serve_command`. Add `test_ui_help` (`skillgate ui --help` exit 0, mentions 127.0.0.1 / no account). |
| `tests/test_oss_surface.py` | Keep deny-list. Add assertions: `local_ui` may exist; `web.py` / `wizard.py` still absent; `cli.py` must not import `uvicorn`. |
| `tests/test_dockerfile.py` | **Unchanged expectations.** Optionally assert `compose.yaml` still has no `ports:`. |
| `fixture_bind.py` docstring | Update: OSS has a **local** setup wizard; generated-check drafts / regression still stay private. |

### 5.3 Do not add

`src/skillgate_ai/web.py`, `wizard.py`, `author.py`, `stage_b.py`, `auth_siwv.py`, `store.py`, React app under `web/`, `EXPOSE` in Dockerfile, Compose service that `CMD ui`, GitHub login buttons, usage telemetry.

---

## 6. Local HTTP API (implementation contract)

All routes are **loopback JSON or static**. No cookies, no `Authorization`, no CORS for other origins (optional `Access-Control-Allow-Origin: http://127.0.0.1:<port>` only).

| Method | Path | Behavior |
| --- | --- | --- |
| GET | `/` | `index.html` |
| GET | `/static/*` | Package files only (path jail). |
| GET | `/api/meta` | `{version, root, has_any_key, demo_default: true, account: false}` |
| GET | `/api/packs` | Discover packs under root (`list` CLI equivalent). |
| POST | `/api/packs` | `{parent, name}` → `scaffold.create_pack`. 400 on `IngestError`. |
| GET | `/api/pack?path=` | `{skill, files, dataset, history_tail}` via ingest + `dataset_view` + `browser_files`. |
| PUT | `/api/pack/skill-md` | Body: frontmatter fields + body. `write_skill_md` then `ingest_skill`. |
| PUT | `/api/pack/cases` | Body: `CasePack` JSON → `save_case_pack`. |
| POST | `/api/pack/fixtures` | `{src}` copy or `{synthesize: true, dest, prompt}`. |
| PUT | `/api/env` | Optional keys; refuse unknown names; write `.env`. 400 if live-only names outside the allowlist. |
| POST | `/api/check` | `{path, live?: false, harness?: "auto", expect_fail?: false}` starts a **background thread**, returns `{run_id, exit_code: null}`. Reuse `live.create_control`. |
| GET | `/api/runs/{id}` | Snapshot: `progress_to_dict` while running; when done `{report: report_to_dict, exit_code}` **exactly** as `gate.run_check` computed. |
| POST | `/api/runs/{id}/kill` | `RunControl` kill. Optional v1. |
| POST | `/api/pack/apply-advice` | `{path, description}` → `rewrite_skill_description`. |

Path params: always resolve, reject `..`, reject non-files for file APIs. Default confine to `--root`. Absolute paths outside root: allow only if they exist and the user POSTed them (picker “Open”), still jail `..`.

**Check thread:** one run at a time in v1 (second POST 409). Matches a local single-user tool.

**Exit equivalent:** JSON field `exit_code` is 0/1/2 with the same rules as Typer. UI header shows it. Tests compare UI `exit_code` to `CliRunner.invoke(..., ["check", ...]).exit_code` on copies of the same pack.

---

## 7. Tests that prove no-account + check 0/1

Existing `tests/conftest.py` already blanks every BYOLLM env var and stubs Codex login. Keep that autouse fixture.

| Test | Proves |
| --- | --- |
| Existing `test_check_pdf_green` / `test_check_sabotaged_red` / `test_check_expect_fail` / `test_check_live_without_key_errors` | CLI still 0/1/2 with no keys. Do not weaken. |
| `test_no_serve_command` | `serve` stays dead. |
| `test_gate_matches_cli_exits` | `gate.run_check(pdf)` exit 0; sabotaged 1; expect-fail 0; live 2. |
| `test_ui_check_sabotaged_json` | POST `/api/check` on a **tmp copy** of pdf-sabotaged, poll until done, `gate=="red"`, `exit_code==1`, `advice.paste` has no grocery/dinner, `passed_count==1`. No `Authorization` header sent. |
| `test_ui_apply_fix_then_green` | Apply `advice.description` on the tmp copy, re-check, `gate=="green"`, `exit_code==0`. |
| `test_ui_new_pack_no_key_green` | Scaffold name-matching folder + trigger-only cases + usable description → check exit 0 with empty keys. |
| `test_ui_name_mismatch_400` | Create `folder=other` with `name=my-skill` → 400, ingest “must match”. |
| `test_ui_meta_no_account` | `/api/meta` → `account is False`, `has_any_key is False` under conftest. |
| `test_ui_does_not_import_hosted` | Import `skillgate_ai.local_ui.server`; AST deny-list still green. |
| `test_dockerfile_is_cli_not_serve` | Unchanged. |
| `test_compose_has_no_ui_ports` | **New:** `compose.yaml` has no `ports:` and default service comment/CMD still check. |

Do **not** require Docker to run the UI in CI. Do **not** add live Cursor keys to gate.yml.

Manual proof (Phase 3 of UI work, like `docs/proof/MATRIX.md`): `skillgate ui --pack skills/pdf-sabotaged`, screenshot optional; captured `GET /api/runs/...` JSON + CLI `--json` diff equal on `gate`, `passed`, `failed_task_ids`, `advice.description`.

---

## 8. Docker (locked)

**UI is a local host process. CLI/Docker `check` stays the gate.**

Do **not**:

- Change `ENTRYPOINT` or `CMD`.
- Add `EXPOSE`.
- Add a `ports:` mapping on the default `skillgate` compose service.
- Make `docker compose run skillgate` start a web server.
- Bake a hosted-style `CMD ["ui", "--host", "0.0.0.0"]` into GHCR.

Document in README / `docs/ui.md`:

```bash
# UI (host Python, after pip install -e .)
skillgate ui

# Gate (unchanged)
docker compose run --rm --no-TTY skillgate
PACK=./skills/pdf-sabotaged docker compose run --rm --no-TTY skillgate   # exit 1
```

**Hunch, reject for v1:** a `profiles: ["ui"]` compose service. It invites `0.0.0.0:8765` and confuses the “never serve” image. Revisit only if users demand it; even then it must be a **non-default profile** and must not alter the runtime stage CMD.

`.dockerignore` already excludes `docs/` and `tests/`; static files live under `src/` so they **will** enter the wheel/image. Harmless: default container argv never starts the server. Image size stays CLI-shaped (no node_modules, no React).

---

## 9. Ordered Phase 2 checklist

Implement in this order on a later PR (not this plan PR):

1. Fix `{orig}` in `case_pack.py` (unblock wizard YAML errors).
2. Extract `gate.run_check` from `cli._run_gate`; point CLI at it; `tests/test_gate.py` + existing check tests green.
3. `write_skill_md` + `scaffold.create_pack` / trigger-only cases; unit tests for name==folder and no-key green.
4. `local_ui.server` + `api.py` (JSON only, no pretty HTML yet) + `tests/test_local_ui.py` red/green/apply.
5. Static wizard HTML/JS/CSS; `skillgate ui` command; `--help` test.
6. Wire Apply + polling + demo banner + optional `.env` writer.
7. Docs: `docs/ui.md`, README/quickstart pointers. Docker section restates ENTRYPOINT/CMD unchanged.
8. `test_oss_surface` still deny `web.py`/`wizard.py`; `test_dockerfile` still forbids `serve`.
9. Proof: pytest; CLI 0/1; UI JSON 0/1 on twins; `docker inspect` entry/cmd unchanged; `skillgate serve` still missing.

---

## 10. Risks

| Risk | Mitigation |
| --- | --- |
| Accidental copy of private `web.py` / `wizard.py` | Deny-list filenames + extract script DENY. New code is `local_ui/`. |
| FastAPI/uvicorn sneak into required deps | Do not add them. Proof grep / pyproject test can stay. |
| `skillgate serve` or Docker `CMD ui` | Tests already fail on `serve` in CLI and Dockerfile. Keep them. |
| UI becomes a cloud app (bind 0.0.0.0, login) | Default host 127.0.0.1; `/api/meta.account=false`; no SIWV modules. |
| BYO key required by UX copy | Step 4 optional; demo banner; tests with blank env. |
| New pack never greens (scaffold includes goldens without scripts) | Default scaffold is trigger-only + negative case. |
| Applying fix mutates CI seed | Tests copy to `tmp_path`. UI confirm if path is the repo seed. |
| `{orig}` NameError | Fix in the implementation PR before wizard save/load. |
| Path traversal via `/api/pack?path=` | `pack._path_under_skill` / resolve + `--root` confine. |
| Progress API copied from hosted eval-slice | OSS `run_eval` already dropped slice/poller from the public gate. Single in-process thread, no `eval_slice`. |
| Port 8477 confusion | Use 8765. Docs say this is not hosted `serve`. |
| `setuptools` omits static files | `package-data` + a test that `local_ui/static/index.html` is importlib-reachable. |

---

## 11. This PR

Docs only:

- `docs/plans/2026-10-04-local-ui-setup-wizard.md` (this file)
- README pointer under Docs

No application code, no `skillgate ui`, no Dockerfile edits, no visibility change, no copy from `skillgate-ai`.
