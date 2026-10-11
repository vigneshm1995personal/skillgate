# Compare runs — Implementation Plan

> **Phase 1 is this plan.** Phase 2+ implement on follow-up branches after Vignesh approves. Do **not** ship product code in this PR. Do **not** bump/publish PyPI from this PR.

**Goal:** Side-by-side **Compare** for one skill on one Dataset (same pinned cases): (1) **models** — N harness configurations on the same pack; (2) **versions** — the same Dataset against two skill snapshots (history runs and/or git refs). Per-case **Pass** / **Fail**, suite aggregates, and **tokens · cost · latency** where the harness records them. Works in **`skillgate ui`** and **`skillgate compare`** with the same engine and history storage.

**Parents:** [`0.5-decisions.md`](0.5-decisions.md) (live-only, explicit keys), [`2026-10-04-local-ui-setup-wizard.md`](2026-10-04-local-ui-setup-wizard.md) (UI ↔ CLI parity). **PR #20** ([`custom-judge-checks.md`](custom-judge-checks.md) on branch `cursor/custom-judge-checks-bac0`, draft, **not merged**) — plan compare against **main @ 0.5.1**; note integration points where #20 lands first.

**Hosted:** private `vigneshm1995personal/skillgate-ai` pins the OSS wheel. **One UI codebase:** `web/` → `web_static/`, same FastAPI shell (`api.py` + route modules). Hosted adds git/remotes and analytics; OSS stays pack-local.

Inspected OSS tree: `main` @ `d7068b2` (**`skillgate-ai` 0.5.1**). CLI **`skillgate`**.

---

## Open questions for Vignesh

Answer before Phase 2 starts. *Italics* are recommendations.

1. **README “Coming soon”.** `main` @ 0.5.1 has no Compare bullet yet. *Recommend:* add a short **Coming soon** subsection in the implementation PR that ships Compare (models or versions), then move the line into the main feature list in that same PR when the slice is done (per product brief). Confirm wording: “Compare models” / “Compare versions” as two lines or one “Compare runs”.
2. **Harness model names in Compare chrome.** Brief: never name **scoring/judge** provider or model in UI/CLI. *Recommend:* Compare columns use **user arm labels** (default “Arm A”, “Arm B”, …). Subtitle may show harness family (Cursor, Codex, Claude) via existing `harness_display_name`; optional “custom model” only when the user typed a non-default model for that arm — or hide slug entirely and show `config.fingerprint` short hash. Which?
3. **Version compare without git.** Packs copied via `skillgate example` may have no `.git`. *Recommend:* **history-only** version compare always works (pick two `run_id`s with matching `pack_fingerprint`); **git ref** mode requires the skill folder to live inside a git work tree. Refuse with a plain error otherwise.
4. **Git ref semantics.** *Recommend:* `skillgate compare versions` checks out **SKILL.md + skill files only** (same allowlist as deploy: exclude `evals/`) at each ref into a temp dir, runs against the **current** `evals/cases.yaml` on disk (Dataset frozen). Alternative: snapshot `evals/` at ref too (harder, changes “same dataset” meaning). Which?
5. **Compare exit code.** *Recommend:* CLI exits **0** when the compare **job finishes** (all arms ran or user-aborted cleanly); exit **1** only when a required arm could not run (missing key, dataset mismatch, spend cap exceeded before start). Do **not** exit 1 just because an arm is red — Compare is observational, not a gate.
6. **Persist compare jobs in history JSONL.** *Recommend:* append `kind: "compare"` rows beside existing `kind: "run"` in `<pack>/evals/history/YYYYMMDD.jsonl` (same directory; `load_history` filters them out of the default run list). OK, or prefer workspace-only `.skillgate/compares.jsonl`?
7. **Order of rollout.** *Recommend:* ship **models compare** first (reuses one pack tree, aligns with Run config UI). **Versions compare** second (git + fingerprint rules). Confirm or flip.
8. **PR #20 merge order.** If #20 merges before Compare: browser API scrub (`provider`, `config.model`, `config_label_raw`, …) becomes mandatory on new `/api/compare/*` payloads. If Compare merges first: rebase onto #20 before release. *Prefer Compare implementation after #20 QA?*

---

## 0. Locked product constraints

1. **One pack on disk** + explicit keys (0.5). Compare runs live harnesses only; no key → exit **2** with the same Settings / `skillgate keys set` copy.
2. **Same Dataset.** All arms in a compare share one `pack_fingerprint` (`case_pack.pack_fingerprint` / `report.pack_fingerprint`). Mismatch → exit **2**, plain message; do not silently drop cases.
3. **Black-and-white UI** (#19 tokens in `web/src/index.css`). **Only Pass / Fail** use green / red (`--success`, destructive). Compare tables use monochrome badges with pass/fail chroma only.
4. **Never name scoring/judge provider or model** in Compare UI or CLI output (tables, summaries, `--json` scrub). Use “Scored by the judge” / omit judge columns. Harness arm labels follow §Open questions 2. Reuse #20 scrub helpers when present.
5. **BYO keys only** in Skill Gate store (`keys.py`, `.skillgate/keys`, `SKILLGATE_*`, `--key-env`). No ambient `OPENAI_API_KEY` / AWS chain for compare runs.
6. **Reuse run storage.** Individual arms append normal **`kind: "run"`** history rows (full `report_to_dict` payloads). Compare job metadata references those `run_id`s. Do not invent a parallel eval database or cloud-only store.
7. **`evals/deploys.jsonl`** stays deploy-only; compare does not write deploy rows.
8. **Docker default** stays `skillgate check /pack`. Compare is optional CLI/UI; not required in the image CMD.
9. **One shared React app** (`web/`). Hosted enables Compare routes; local mode uses real pack paths. No second compare UI in `local_ui/static/`.

---

## 1. What exists today (inspected code paths)

### 1.1 Single-run pipeline (what Compare orchestrates)

| Piece | Path | Role for Compare |
| --- | --- | --- |
| Gate | `src/skillgate_ai/gate.py` — `run_check`, `persist_eval` | One arm = one `run_check` with distinct `EvalRunConfig` / `run_id`. |
| Engine | `src/skillgate_ai/engine.py` — `run_eval`, `SuiteReport.usage_totals` | Per-task `usage` (tokens, `cost_usd`); suite roll-up. |
| Usage parse | `src/skillgate_ai/usage.py` | Harness-reported tokens/cost only; never estimate dollars from tokens. |
| Report | `src/skillgate_ai/report.py` — `report_to_dict`, `scored_by_line` | History embeds full task list, `pack_fingerprint`, `usage`, `metrics`. |
| History | `src/skillgate_ai/history.py` — `append_eval`, `load_history`, `latest_eval` | Append-only `<pack>/evals/history/YYYYMMDD.jsonl`; rows have `run_id`, `report`, `config`. |
| Deploy log | `history.py` — `append_deploy`, `load_deploys` | Separate `evals/deploys.jsonl`; unrelated to compare. |
| Config stamp | `src/skillgate_ai/eval_config.py` — `EvalRunConfig`, `config_fingerprint`, `customer_config_label`, `customer_run_details` | Arm labels for UI/CLI; fingerprint diff detection. |
| Dataset fingerprint | `src/skillgate_ai/case_pack.py` — `pack_fingerprint`, `PACK_FINGERPRINT_FIELDS` | Gate for “same dataset” across arms / history picks. |
| Skill body hash | `src/skillgate_ai/pack.py` — `skill_pack_hash` | Version identity for skill **files** (exclude evals). |
| UI runs | `src/skillgate_ai/api_runs.py` — `POST /api/runs`, poll | Today one concurrent run (`409` if busy). Compare needs a **compare session** or queue. |
| History API | `src/skillgate_ai/api_payloads.py` — `history_row_to_run`, `history_payload`, `run_from_history` | Run picker for version compare; `baseline` stub in payloads. |
| Metrics display | `web/src/lib/metrics-label.ts` | `tokenMetricDisplay`, `costMetricDisplay`, `runMetricsLine` — reuse in Compare grid. |
| Baseline (related) | `web/…/gate-page.tsx`, `history-page.tsx`, `api_shims.py` `POST /api/evals/baseline` | Pin one run; regression hints. Compare is multi-arm, not baseline replacement. |
| Live elapsed | `src/skillgate_ai/live.py` — `elapsed_sec` in progress | UI shows elapsed during run; **not** persisted in history today → Phase 2 adds per-task `duration_sec` on compare arms (see §4). |

### 1.2 UI / CLI surfaces

| Piece | Path | Fact |
| --- | --- | --- |
| React app | `web/src/App.tsx` | Stages: home, eval, deploy, repository, **history**, settings. No Compare stage yet. |
| Sidebar | `web/src/components/dashboard/app-sidebar.tsx` | Pattern for new **Compare** nav row (`id="tab-compare"`). |
| History list | `web/src/components/dashboard/history-page.tsx` | Filterable timeline; run meta via `history-meta.ts`. |
| CLI | `src/skillgate_ai/cli.py` | `check`, `deploy`, `keys`, … — no `compare` group. |
| Package UI | `skillgate ui` → `api.py` + built `web_static/` | Same bundle as hosted (`docs/ui.md`). |
| Hosted shims | `src/skillgate_ai/api_shims.py` | Stubs for cloud-only routes; Compare OSS routes must not 404 in hosted when feature-flagged on. |

### 1.3 PR #20 (draft, not merged) — integration only

Do **not** depend on unmerged code in Phase 2 planning baseline; when #20 lands:

| #20 change | Compare impact |
| --- | --- |
| BYO judge providers + extras | Compare pass/fail still driven by `task.passed` + det scorers; extra judge cells are not separate compare columns unless product asks later. |
| Browser API scrub on `/api/history`, `/api/runs/*` | New `/api/compare/*` responses must apply the **same** redaction (`provider`, `backend`, `config.model`, `config_label_raw`, …). |
| `config` / fingerprint includes judge | Version compare should treat judge config as part of arm stamp when comparing **models**; optional “same scoring settings” guard. |
| Copy: “Scored by the judge” | Compare aggregate footer uses the same line; never per-provider names. |

Implementation branch should rebase onto `main` after #20 merge and run full pytest + vitest before release.

---

## 2. Feature definitions

### 2.1 Models compare

- **Input:** one skill pack path; **2–4 arms** (product cap, see §7).
- Each arm: harness pref (`auto` \| `cursor-agent` \| `codex` \| `claude` \| `llm`), optional model, timeout, temperature, reasoning effort — same fields as Run (`eval_config.EvalRunConfig`).
- **Execution:** sequential arms (reuse single-run engine; avoid N parallel harnesses on one machine unless Vignesh later opts in). Each arm → `run_check` → normal history `kind: "run"` row.
- **Output:** matrix **cases × arms** with Pass/Fail; footer per arm: `passed_count/task_count`, sum tokens/cost, wall latency; highlight disagreements (any case where arms differ).

### 2.2 Versions compare

- **Input:** one skill pack; **two versions**:
  - **History mode:** two `run_id`s from `load_history` on that pack, same `report.pack_fingerprint`, different `skill_pack_hash` or `config` optional.
  - **Git mode (optional v2):** two refs (`main`, `v1.2.0`, commit sha) resolving skill files via `git show ref:path` or short worktree; Dataset = current `evals/cases.yaml`.
- **Execution:** for git mode, materialize skill snapshot per ref, point `run_check` at temp skill root while keeping evals on the pack (see §Open questions 4). For history mode, **no re-run** — hydrate from stored `report` (read-only compare). Offer “Re-run both” as a button that creates a new models-style compare with two configs stamped from those runs.
- **Output:** same case matrix; version columns show Pass/Fail + metrics from the chosen runs; optional diff summary (“3 checks flipped Pass → Fail”).

---

## 3. Data model — compare job

Stored as one JSON object (history row or API record). IDs: `compare_id` (12-char hex, like `run_id`).

```json
{
  "ts": "2026-10-11T22:00:00-04:00",
  "kind": "compare",
  "compare_id": "c0mpare12ab",
  "mode": "models",
  "skill": "pdf",
  "pack_fingerprint": "sha256…",
  "pack_case_ids": ["extract-hello", "…"],
  "status": "done",
  "arms": [
    {
      "arm_id": "a",
      "label": "Arm A",
      "source": "live",
      "run_id": "abc123",
      "config_fingerprint": "…",
      "passed": false,
      "passed_count": 6,
      "task_count": 8,
      "usage": { "tokens_total": 120000, "cost_usd": 0.42 },
      "duration_sec": 380.5
    }
  ],
  "cases": [
    {
      "case_id": "extract-hello",
      "results": {
        "a": { "passed": true, "usage": { "tokens_total": 9000 }, "duration_sec": 41.2 },
        "b": { "passed": false, "usage": { "tokens_total": 11000 }, "duration_sec": 52.0 }
      },
      "disagreement": true
    }
  ],
  "spend": { "cap_usd": 5.0, "spent_usd": 0.42, "stopped_reason": null },
  "error": null
}
```

**Version mode** arms add `skill_pack_hash`, `history_run_id` or `git_ref`, and `source: "history" | "live" | "git"`.

**Invariants**

- `pack_fingerprint` matches every embedded run report used.
- Each live arm has a backing `run_id` in the same pack’s history JSONL.
- `cases[].results` keys match `arms[].arm_id`.
- No judge provider/model fields in customer-facing export (scrubbed copy for API/CLI).

---

## 4. Latency and metrics

| Metric | Source today | Compare v1 |
| --- | --- | --- |
| Tokens / cost | `task.usage` / `usage_totals` | Sum per arm; per-cell from task row. |
| Path steps | `task.metrics.path` | Optional column; not primary compare signal. |
| Wall latency | Live poll `elapsed_sec` only | **Add** `duration_sec` per task in report payload during compare runs (engine timestamps around each task). History-only version compare uses stored value when present; else show “—”. |

Display rules match `metrics-label.ts`: never invent cost from tokens; show “not recorded” when missing.

---

## 5. CLI UX

New Typer group: `skillgate compare` (human-first; `--json` for machines).

```
skillgate compare models PACK [OPTIONS]
skillgate compare versions PACK [OPTIONS]
skillgate compare show COMPARE_ID [--skill PACK]
skillgate compare list PACK [--limit 20]
```

### 5.1 `compare models`

```bash
# Two arms via repeatable --arm (label:harness[:model] shorthand)
skillgate compare models pdf \
  --arm "Cursor default:cursor-agent" \
  --arm "Codex default:codex"

# Full config per arm (JSON file or inline)
skillgate compare models pdf \
  --arm-file arms/cursor.json \
  --arm-file arms/codex-gpt.json

# Guardrails
skillgate compare models pdf --arm "A:codex" --arm "B:codex" \
  --max-spend-usd 5 \
  --cases extract-hello,extract-invoice   # optional subset

skillgate compare models pdf --arm "A:codex" --arm "B:codex" --json
```

| Flag | Purpose |
| --- | --- |
| `--arm LABEL:HARNESS[:MODEL]` | Repeatable; 2–4 arms. |
| `--arm-file PATH` | JSON matching `EvalRunConfig` draft + `label`. |
| `--max-spend-usd N` | Stop before next arm if summed `cost_usd` ≥ N (see §7). |
| `--max-tokens N` | Optional token ceiling across arms. |
| `--cases id1,id2` | Subset; default all pinned cases. |
| `--dry-run` | Print plan + estimated case count; no API calls. |
| `--json` | Emit compare object (scrubbed). |
| `--key-env` | Same as `check`. |

**Exit codes:** **0** completed; **1** compare invalid / arm failed to start; **2** missing key / bad args / dataset mismatch / spend cap blocked start.

Human summary (no judge names):

```
Compare · pdf · models · 8 checks · 2 arms
Dataset fingerprint  a1b2c3…

              Arm A          Arm B
              Cursor         Codex
Checks        6/8 Pass       7/8 Pass
Tokens        120k           98k
Cost          $0.42          $0.31
Latency       6m 20s         5m 05s

Case               Arm A    Arm B
extract-hello      Pass     Pass
extract-invoice    Fail     Pass
…

3 cases disagreed. Full JSON: skillgate compare show c0mpare12ab --json
```

### 5.2 `compare versions`

```bash
# History (no re-run)
skillgate compare versions pdf --run abc123 --run def456

# Git (when enabled)
skillgate compare versions pdf --git HEAD --git main~1

# Re-run both arms with configs taken from those runs
skillgate compare versions pdf --run abc123 --run def456 --rerun
```

Validation: same `pack_fingerprint`; else exit **2** with both fingerprints shown.

### 5.3 `compare show` / `list`

- `show` reads compare row from pack history (or workspace index) by `compare_id`.
- `list` newest compare jobs for a pack.

---

## 6. UI wireframe (text)

**Entry:** Sidebar **Compare** (`tab-compare`) between **History** and **Settings**.

**Page header:** `Compare` — “Run the same Dataset on multiple setups or skill versions.”

```
┌─────────────────────────────────────────────────────────────────┐
│ Compare                                                          │
│ Skill [ pdf ▼ ]          Mode ( Models | Versions )              │
├─────────────────────────────────────────────────────────────────┤
│ MODELS                                                           │
│  Arm A  [Label________]  Harness [ Codex ▼ ]  Model [ default ] │
│  Arm B  [Label________]  Harness [ Cursor ▼ ]  Model [ default ] │
│  [ + Add arm ] (disabled at 4)                                   │
│  Spend cap [ $5.00 ]   Cases [ All pinned ▼ ]                     │
│  [ Dry run ]  [ Run compare ]                                    │
├─────────────────────────────────────────────────────────────────┤
│ VERSIONS                                                         │
│  ○ Pick two history runs   [ run abc… ▼ ]  [ run def… ▼ ]        │
│  ○ Git refs (if repo)      [ main ]  [ v1.0 ]                    │
│  [ Compare ]  [ Re-run both with same settings ]                 │
├─────────────────────────────────────────────────────────────────┤
│ RESULT (after run)                                               │
│  ┌──────────────┬─────────┬─────────┐                            │
│  │ Check        │ Arm A   │ Arm B   │  ← only Pass/Fail colored  │
│  ├──────────────┼─────────┼─────────┤                            │
│  │ extract-…    │ Pass    │ Fail    │                            │
│  └──────────────┴─────────┴─────────┘                            │
│  Arm A · 6/8 Pass · 120k tok · $0.42 · 6m 20s                    │
│  Arm B · 7/8 Pass · 98k tok · $0.31 · 5m 05s                     │
│  Scored by the judge (when applicable) — single line, no vendor    │
│  [ Open arm A run ] [ Open arm B run ] [ Export JSON ]           │
└─────────────────────────────────────────────────────────────────┘
```

**Interactions**

- While running: reuse Checking → slide → drawn Pass/Fail **per arm** in progress drawer (sequential arms).
- Row click opens existing Result panel for that arm’s `run_id`.
- `prefers-reduced-motion`: no new animations beyond existing eval hold.
- Hosted: same components; git ref fields hidden when `status.mode === "local"` and pack has no git root.

**API (OSS)**

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/compare/models` | Body: skill, arms[], spend_cap, case_ids?. Returns `{ compare_id, status }`. |
| `POST` | `/api/compare/versions` | Body: skill, run_ids[] or git_refs[]. |
| `GET` | `/api/compare/{compare_id}` | Poll scrubbed compare payload. |
| `GET` | `/api/compare?skill=pdf` | List recent compares. |

Server holds compare job in `AppState` (extend `api_payloads.AppState` or parallel dict) with lock; only one **compare** or **run** at a time initially (same 409 pattern as `api_runs.py`).

---

## 7. Cost guardrails

| Guard | Default | Behavior |
| --- | --- | --- |
| Max arms | 4 | CLI/UI validation |
| Max cases | all pinned | Optional subset; seed packs still respect pinned |
| `max_spend_usd` per compare | **$5** (user override in UI Settings → Compare or `.skillgate/settings.json`) | Before each arm: if sum of prior arms’ `usage.cost_usd` ≥ cap, stop with `stopped_reason: "spend_cap"`; partial compare still saved |
| `max_tokens` (optional) | unset | Same pattern on `tokens_total` |
| Pre-flight | dry-run | Show `arms × cases` count; warn if any arm uses empty model default |
| No estimate from tokens | locked | Do not invent dollars when harness omits `cost_usd` |

Spend cap is **compare-wide**, not per arm. Keys remain user-owned; Skill Gate never pays.

---

## 8. Files to create / modify (Phase 2+)

### 8.1 Create

| Path | Why |
| --- | --- |
| `src/skillgate_ai/compare.py` | Orchestrate arms, build compare payload, spend checks, dataset validation |
| `src/skillgate_ai/compare_git.py` | Optional git snapshot of skill files (versions mode) |
| `tests/test_compare_models.py` | Dataset mismatch, arm sequencing, spend cap, scrubbed JSON |
| `tests/test_compare_versions.py` | History hydration, fingerprint guard |
| `tests/test_compare_cli.py` | Typer exit codes, `--json` shape |
| `web/src/components/dashboard/compare-page.tsx` | Compare UI |
| `web/src/lib/compare.ts` | Types, scrub helpers, table builders |
| `web/src/lib/compare.test.ts` | Disagreement detection, metric rows |

### 8.2 Modify

| Path | Why |
| --- | --- |
| `src/skillgate_ai/history.py` | `append_compare`, `load_compares`; filter `kind=="compare"` out of `load_history` |
| `src/skillgate_ai/cli.py` | `compare` command group |
| `src/skillgate_ai/api_compare.py` | Register routes; wire to `compare.py` |
| `src/skillgate_ai/api.py` | Import `register_compare_routes` |
| `src/skillgate_ai/engine.py` / `report.py` | Optional `duration_sec` on tasks when `source=compare` |
| `src/skillgate_ai/api_payloads.py` | Scrub helper shared with runs (or import from #20) |
| `web/src/App.tsx`, `app-sidebar.tsx`, `types.ts`, `api.ts`, `dashboard-provider.tsx` | Stage + nav + API client |
| `README.md` | Coming soon → feature list when each slice ships |
| `docs/ui.md`, `docs/pack.md` | Compare + history `kind` |
| `tests/test_oss_surface.py` | If new public strings must avoid judge vendor leaks |

### 8.3 Do not change in compare PRs

- Docker `ENTRYPOINT` / default `CMD`
- Seed `skills/pdf` case contents
- `evals/deploys.jsonl` schema
- Checking motion constants in `web` (700 / 350 / 400) except wiring compare progress

### 8.4 Hosted (`skillgate-ai` private)

- Pin wheel with compare module.
- Enable Compare nav; implement git ref picker against connected repo when not local.
- Reuse OSS scrubbed API types; no forked compare table.

---

## 9. Test plan

**TDD** per `test-driven-vibe`: failing tests first, then implementation.

### 9.1 Unit / integration (pytest)

1. Models compare with two mocked arms → one `kind: "compare"` row + two `kind: "run"` rows.
2. `pack_fingerprint` mismatch across arms → exit **2**, no partial writes.
3. Spend cap stops before arm 3; compare payload records `stopped_reason`.
4. Scrubbed `--json` has no `judge.provider`, `judge.model`, or `config_label_raw`.
5. Versions history mode: two fixture history rows → matrix without `run_check` calls.
6. Git mode refused when `.git` missing.
7. `load_history` still returns only runs; `load_compares` returns compare rows.
8. Parallel with existing: `test_history.py`, pdf/sabotaged contracts, keyless exit **2**.

### 9.2 Web (vitest)

1. Compare table marks disagreement when passes differ.
2. Metrics cells show “—” when usage null.
3. Arm labels render; no OpenAI/Jev/AWS strings in snapshot fixtures.
4. Mode toggle models vs versions.

### 9.3 Live proof (manual / optional CI with secrets)

1. `skillgate compare models` on `skills/pdf` with two harness prefs (Cursor + Codex) and real keys — 8 rows, costs recorded if harness reports them.
2. UI Compare page matches CLI matrix for same `compare_id`.
3. After #20: verify API responses in browser devtools contain no scrubbed fields.

Run full suite before push: `pytest -q`, `pnpm --dir web test`, `gate` keyless exit 2, `web-build`, `oss-surface`, docker job per `AGENTS.md`.

---

## 10. Risks and migrations

| Risk | Mitigation |
| --- | --- |
| PR #20 API scrub drift | Shared redaction function; rebase before release |
| Compare + single run concurrency | Serialize on `AppState.lock`; clear UX “compare running” |
| Git ref compare surprises (evals vs skill) | Document §2.2; Open question 4 |
| History JSONL growth | Compare rows are small vs full reports; arms still store full reports as today |
| Latency missing on old runs | Show “—”; optional re-run |
| Hosted-only git | OSS history mode still ships |
| Judge extras change pass semantics (#20) | Compare uses final `task.passed` only |

**Migration:** None for existing packs. First compare append is additive JSONL. No schema bump for `cases.yaml`.

---

## 11. Phased rollout

| Phase | Ships | README |
| --- | --- | --- |
| **2a** | `compare models` CLI + engine durations + history `kind: compare` | Move “Compare models” from Coming soon → features |
| **2b** | UI Models compare + API routes | — |
| **3a** | `compare versions` history mode | Move “Compare versions” → features |
| **3b** | Git ref mode (if approved) | docs note git requirement |
| **Hosted** | Pin wheel; cloud git picker | — |

**Order:** **Models first**, then **versions** (§Open questions 7).

---

## 12. Out of scope (this plan and v1)

- Parallel multi-arm harness execution on one host
- Compare across **different** skills or datasets in one job
- Marketplace / billing for compare
- Vanilla `local_ui/static/` compare page
- Naming judge/scoring vendors in compare output
- Inventing latency or cost metrics
- Depending on unmerged #20 code in the first commit (rebase when it lands)

---

## 13. This PR (Phase 1)

- **Only** `docs/plans/compare.md` on branch `cursor/compare-plan`.
- Draft PR for Vignesh review. **Stop** — no implementation until approved.
