# Skill Gate UI revamp — Implementation Plan

> **Updated for Skill Gate 0.5.0 on `main` (`7a0ab4e`).** This PR is the plan. Product CSS/TSX ships on a **sibling branch** off `main` (do **not** merge either until Vignesh says so). Do **not** copy a second UI into hosted `skillgate-ai`. Do **not** run live model-cost Evaluate.

**Goal:** One shared React UI in this repo’s `web/` for OSS (`mode=local`) and paid (`mode=cloud`). Revamp it so it is not a generic AI dashboard, while keeping the Gate motion Vignesh already likes. Hosted `skillgate-ai` consumes this UI unchanged.

**Skills:** `plan-mode`, `clean-coder`, `test-driven-vibe`, `frontend-design`, `error-driven-debugger`. Runtime kit stays **shadcn** (`web/components.json` `base-nova`). daisyUI is a semantic-color reference only.

**Parents:** [`docs/plans/0.5-decisions.md`](0.5-decisions.md) (live-only, explicit keys, examples). One-codebase rule: OSS and paid have the **same UI code**.

**Inspected:** `origin/main` @ `7a0ab4e` (0.5.0). Shared `web/` is on main. PR #13 has landed via 0.5.0.

---

## For Vignesh (plain English)

- One set of screens. Local `skillgate ui` and hosted skill-gate-ai.app both render `web/` from **this** repo.
- 0.5.0 flow: Connect Cursor / Codex / Claude → Skills list → skill page → Dataset → press **Run** (needs a key in Settings) → results → Deploy. Paid chrome is **hidden**, not locked. No built-in checker. No key → Run disabled; CLI `check` exits 2.
- Keep Checking hold, slide, drawn Passed/Failed mark, rows-then-stamp, Result | Check | What happened (row opens to the five answers).
- Kill the generic look: purple dark-mode sidebar accent, Geist on every role, identical rounded cards, landing as a second palette.
- Customer words only. Leftovers still in 0.5.0: “Import YAML”, “Cursor Agent harness”, “Browse all in Repository”, “Eval spend”, “Config changed”, landing “pack hash / semver”, ISO times on hover, skill-page run rows that do not open.
- Gate badges are already Ready / Blocked / Pending (not GREEN/RED). Keep Ready/Blocked.
- First shipping PR: tokens + primitives + this copy pass. Later PRs restyle screens. Hosted picks up `web/` unchanged.

---

## 0. Locked product rules (0.5.0)

1. **One UI.** OSS and paid share `web/`. Hosted must not keep a second dashboard after consume.
2. **Keep the Gate ritual.** Checking hold (≥700ms), 350ms slide, 400ms drawn mark, rows-then-stamp, Result | Check | What happened, five answers. `prefers-reduced-motion` skips replay. Do not rewrite `eval-result-hold.ts` / `eval-result-shell.tsx` / `eval-result-mark.tsx` logic.
3. **Live-only.** No demo harness, no “built-in checker”. Run is disabled until Settings (or `skillgate keys`) has a key. CLI keyless `check` exits **2**.
4. **Do not auto-run.** Connect, open skill, load Dataset must not start a check.
5. **Cloud chrome is hidden in local, not locked.** Slots: `signIn`, `billing`, `sharedHistory`, `hostedJudge`, `sandboxes`, `tryoutCaps`, `generateChecks`, `gitPublish`, `suggestUpdates`, `analyticsHome` (+ `macHelper` when helper UI is in this tree).
6. **Customer copy.** No SIWV, Jev, SoR, Hobby, Mini, harness, YAML, pack hash, semver-as-column-title, `evidence_action_validity`, absolute `/root` paths, raw `eval` badges. Code ids may stay (`evalTab`, `harnessPref`).
7. **No model-cost runs** for this work. QA: UI idle screens + keyless CLI exit 2 + recorded motion against fixtures without calling a live model.
8. **shadcn stays.** Reuse components. Do not add daisyUI.
9. **Small diffs.** Tokens and copy first. Do not rewrite routing, eval state, or the FastAPI contract.
10. Docker image stays CLI (`check /pack`). UI is `skillgate ui` on the host.

---

## 1. What 0.5.0 already shipped vs leftovers

### Already customer-plain (do not regress)

| Surface | 0.5.0 |
| --- | --- |
| GateBadge | **Ready** / **Blocked** / **Pending** |
| Skills local blurb | Connect Cursor, Codex, or Claude (no `~/.cursor/skills` in the React tree) |
| Connect | Dialog “Connect”, not a wizard |
| Settings store | `{project}/.skillgate/keys`, not `.env` |
| YAML accordion title | Was “Power user: YAML”; now “Import checks from YAML” — **still jargon** |
| GREEN/RED labels | Gone from chrome |

### Leftovers this revamp still owes

| Visible string | Where | Replace with |
| --- | --- | --- |
| `Import checks from YAML` / `Import YAML` / `Load YAML` | Checks | “Import a list” / “Load list” |
| `Cursor Agent harness` | Settings | “Runs checks in Cursor” |
| `Browse all in Repository` | Evaluate Skill tab | “Browse all skills” |
| `Eval spend` / `Eval runs` / “eval spend” in Home description | Home (cloud slot) | “Spend” / “Runs” |
| `Config changed` | History, skill runs | “Settings changed from the last run” |
| `pack hash` / `semver` | Landing dual band; skill Versions heading | “Version”; drop hash from customer chrome |
| ISO `title={created_at}` | History, Home, Skills, skill page | Readable datetime (`absoluteTime`) |
| Skill **runs** table rows don’t open | `skill-detail-page.tsx` | Click → Gate for that run (`openHistoryRun`) |
| Cloud CTA `Start Evaluations` | Evaluate | “Start” |
| Cloud Skills blurb “evals” | Skills | “runs” |

### Tokens today (`web/src/index.css`)

Still the generic nova sheet: pure white, Geist for heading **and** body, `--radius: 0.75rem`, dark `--sidebar-primary: oklch(0.488 0.243 264.376)` (**purple**). `--success` exists; **no `--warning`**. Landing CSS module is a second palette. Motion CSS (slide / mark / bar) is good — keep timings.

Local flow on disk: Connect → Skills (`repository` is default home in local) → skill page / SKILL.md → Dataset → Evaluate Checks → **Run** → Gate stamp + table → Deploy into Cursor / Codex / Claude folders.

---

## 2. Design tokens (first product PR)

Single source: `web/src/index.css`. Landing maps `--sg-*` onto these.

### Type

| Token | Face | Use |
| --- | --- | --- |
| `--font-sans` | Geist Variable (keep) | Body, nav, tables, forms |
| `--font-heading` | Geist Variable | Page / card titles |
| `--font-display` | **Newsreader** | Stamp “Checking / Passed / Failed” and landing H1 only |
| `--font-mono` | ui-monospace | Pairing codes / paste — never labels |

Do **not** load Inter. Do not put Newsreader on buttons or table headers.

### Color

Warm paper, not pure white. Dark sidebar-primary becomes ink/paper — **not hue 264**. Add `--warning` (amber) for settings-changed / unsure / stale. Pass / fail / warn meet WCAG AA. Status is never color-only (word + mark).

### Radius / elevation / motion

`--radius: 0.5rem`. Stamp mark stays a circle. Flatten stacked cards. **Do not change** `CHECKING_MIN_MS = 700`, `EVAL_MOTION_MS = 350`, or the 400ms mark stroke. Name those durations as CSS variables that match the JS constants.

---

## 3. First product PR (tokens + copy + chrome)

**Branch off `main`.** Keep motion state machines untouched.

| Change | Files |
| --- | --- |
| Tokens, kill purple, `--warning`, display font | `web/src/index.css`, `web/package.json` (Newsreader), `web/src/main.tsx` or css import |
| `Badge` `success` / `warning` variants; GateBadge uses `success` | `web/src/components/ui/badge.tsx`, `chrome.tsx` |
| `absoluteTime()` for tooltips | `web/src/lib/time.ts` |
| Copy pass | landing, eval-page YAML + Repository link + Start, settings hints, home KPIs, history/skill “Config changed”, skill Versions heading |
| Skill runs rows open Gate | `skill-detail-page.tsx` |
| Skip link + `id="main"` | `App.tsx` |
| Deny-list + time tests | `web/src/lib/copy.ts` + `*.test.ts` (TDD) |

**Out of this first PR:** full per-screen layout rewrite, Mac helper port, hosted consume, live Evaluate.

---

## 4. Later phases (after the first PR)

1. **Gate / Evaluate restyle** — display font on stamp only; table spacing; live region on `#run-progress`; keep columns and five questions.
2. **Skills, skill page, History, Home, Settings, empty/error** — fewer nested cards; mosaic stays a cloud slot.
3. **Deploy slots** — local folder copy; cloud Mac helper + git publish in this `web/` (port hosted #158 if missing), then tokens.
4. **Landing + sign-in** — jargon-free; refresh screenshots.
5. **Hosted consume** — pin this package, `SKILLGATE_MODE=cloud`, delete hosted `web/src/components/dashboard/*`.

---

## 5. Per-screen (0.5.0 before → after)

| Screen | Mode | Before (problems) | After |
| --- | --- | --- | --- |
| Landing | C | Dual palette; pack hash / semver | Shared tokens; “Each version is recorded…” |
| Sign-in | C | Generic card | Paper/ink; “This account isn’t invited yet.” |
| Home | C slot | Eval spend / ISO | Runs / Spend; readable dates; hidden in local |
| Skills | L+C | Cloud “evals”; ISO | Connect stays; “runs”; readable dates |
| Connect | L | OK | Keep dialog; no wizard; no raw home paths |
| Skill page | L+C | Runs don’t open; Config changed; semver heading | Rows open Gate; “Settings changed”; Version |
| Evaluate | L+C | YAML; Repository; Start Evaluations | Import a list; Browse all skills; Run / Start |
| Gate | L+C | Generic card around a good stamp | Display serif on Checking/Passed/Failed only; motion unchanged |
| History | C or local JSONL | Config changed; ISO | Plain badge; readable tooltip |
| Deploy | L folders / C helper | Hash in version line if present | Customer paths only; helper is a slot |
| Settings | L+C | Cursor Agent harness | Runs checks in Cursor / Codex / … |

---

## 6. Accessibility (every UI PR)

- Contrast AA; pass/fail not color-only; visible focus; keyboard on tabs/dialogs/check rows.
- Skip link to `#main`.
- `aria-live="polite"` on Checking progress (Gate restyle PR).
- Reduced motion already covers Gate; extend to new row-open.
- Readable date tooltips, not ISO.
- Dialog titles required (shadcn).

---

## 7. How hosted consumes this UI

Freeze visual work on `skillgate-ai/web` (hotfixes only). Public wheel already ships `web/dist`. Hosted: `SKILLGATE_MODE=cloud`, serve `skillgate_ai/web_static`, keep auth/vault/Neon/Jev/helper APIs. CI fails if hosted still has `web/src/components/dashboard/eval-page.tsx`. Until consume, do not restyle the hosted copy.

---

## 8. QA + recording (no model cost)

**Never** press live Run with Cursor/Codex/OpenAI keys for this work.

### Automated (must match GHA before every push)

1. **test** — `GITHUB_ACTIONS=true FORCE_COLOR=1` then `pnpm --dir web test` and `pytest -q`
2. **gate** — `skillgate example pdf --dest /tmp/pdf` && `skillgate ingest /tmp/pdf` && keyless `skillgate check /tmp/pdf` exits **2**
3. **web-build** — `python -m build` && `tests/assert_wheel_ui.py` && wheel `skillgate ui` serves React `mode=local`
4. **oss-surface** — `pytest -q tests/test_oss_surface.py tests/test_dockerfile.py`
5. **docker** — build runtime image; keyless `check` exits **2**

Vitest: motion constants 700/350; five-question order; `mode=local` hides sign-in/Home; copy deny-list; `absoluteTime`; no purple `264.376` in `index.css`.

### Recording

Local `skillgate ui`: Skills → Connect copy → skill page idle (no auto-run) → theme toggle. Do **not** Run live. Optional: mount Gate with a **fixture JSON** later for Checking→Failed/Passed; not in the first tokens PR.

---

## 9. Risks

| Risk | Mitigation |
| --- | --- |
| Motion regression | Do not edit hold/shell/mark logic; Vitest on constants |
| Two UIs drift | One `web/`; hosted consume is a later PR |
| Display font FOUC | Import next to Geist in `index.css` |
| Copy grep false positives | Deny-list user-visible strings in `web/src/components/**/*.tsx` only, not `web/src/lib` ids |

---

## 10. This plan PR vs the product PR

| PR | Contains |
| --- | --- |
| **This one (#17)** | `docs/plans/ui-revamp.md` + README pointer. Rebased onto 0.5.0 `main`. |
| **Sibling off `main`** | Tokens, copy, chrome, tests, before/after screenshots. |

No FastAPI contract change. No PyPI publish. Do not merge until asked.
