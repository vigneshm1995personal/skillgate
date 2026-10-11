# Skill Gate UI revamp — Implementation Plan

> **This document is Phase 1 (plan only).** Do **not** change `web/` CSS, components, copy, or motion in this PR. Do **not** push to [`cursor/react-ui-local-mode-3b9f`](https://github.com/vigneshm1995personal/skillgate/pull/13). Do **not** copy a second UI into hosted `skillgate-ai`. Do **not** run live model-cost Evaluate.

**Goal:** One shared React UI in this repo’s `web/` for OSS (`mode=local`) and paid (`mode=cloud`). Revamp it so it is not a generic AI dashboard, while keeping the Gate motion Vignesh already likes. Hosted `skillgate-ai` consumes this UI; it must not keep its own copy.

**Skills applied:** `plan-mode`, `frontend-design`, `clean-coder` (this repo `.cursor/skills`, landed on `main` in #15). Also read hosted `vigneshm1995personal/skillgate-ai` `.cursor/skills/shadcn` and `.cursor/skills/daisyui`. Runtime kit stays **shadcn** (already in `web/`). daisyUI is a semantic-color reference only — do not add daisyUI CSS.

**Parent (locked):** [`docs/plans/one-codebase.md`](https://github.com/vigneshm1995personal/skillgate/blob/cursor/one-codebase-plan-3b9f/docs/plans/one-codebase.md) on PR #12. Vignesh’s rule: OSS and paid have the **same UI code**.

**Inspected (read-only):**

| Tree | SHA / note |
| --- | --- |
| This repo `main` | `6d8e551` (`Add Cursor agent skills and AGENTS.md` #15) |
| PR #13 `cursor/react-ui-local-mode-3b9f` | `87695ad` — React `web/` being moved here; still in progress; **do not push to it** |
| Hosted `skillgate-ai` | `main` after #158 (Deploy git + Mac helper) and #159 (skills). Still a full copy of `web/` |
| Live screenshots | prod Gate pass (`report-writer`, 5/5), prod Gate fail (`pdf-sabotaged`, 0/8), QA Deploy helper (`csv-clean`, Skill Gate box Linux) |

---

## For Vignesh (plain English)

- One set of screens. Local `skillgate ui` and hosted skill-gate-ai.app both render `web/` from **this** repo. Hosted stops keeping a second copy.
- Keep Checking → slide → drawn Passed/Failed, rows-then-stamp, and Result | Check | What happened (row opens to the five answers). That motion is the product, not decoration.
- The rest of the UI today looks like a generic shadcn dashboard: Geist everywhere, the same rounded card on every page, and a purple sidebar accent in dark mode. Landing is a different dark site. The revamp gives one ink/paper system with pass, fail, and warn as first-class colors.
- Customer words only: skill, check, run, passed, failed, open, blocked. Drop leftover jargon (Power user: YAML, Harness, Config changed, pack hash, semver, `~/.codex/skills`, raw `eval` badges, ISO times on hover, GREEN/RED).
- First shipping work is tokens + shared components. Screen restyles follow after #13 merges. No live Evaluate in this work — no model cost.
- Hosted Deploy already has “Install on your Mac” + git publish (#158). Those stay **slots** in the shared UI (`mode=cloud`), not a hosted-only fork.
- Local home is Skills. Cloud may keep an analytics Home as a hidden-in-local slot. Sign-in and landing exist only in cloud.
- This PR is the plan. No product CSS or TSX.

---

## 0. Locked product rules

1. **One UI.** OSS and paid share `web/`. Hosted consumes it (`mode=cloud`). Hosted must not keep `web/src/components/**` after the consume PR.
2. **Keep the Gate ritual.** Checking hold (≥700ms), 350ms slide, 400ms drawn mark, rows-then-stamp, Result | Check | What happened, five answers. `prefers-reduced-motion` already skips replay — keep it.
3. **Do not auto-run.** Opening a skill, importing, or loading Dataset must not start a check. Run is a button.
4. **Cloud chrome is hidden in local, not locked.** Slots from #12: `signIn`, `billing`, `sharedHistory`, `hostedJudge`, `sandboxes`, `tryoutCaps`, `generateChecks`, `gitPublish`, `suggestUpdates`, `analyticsHome`. Add `macHelper` for #158 pairing (cloud). Local Deploy is copy-into-folders.
5. **Customer copy.** No SIWV, Jev, SoR, Hobby, Mini, harness, YAML-as-power-user, pack hash, semver, `evidence_action_validity`, absolute paths, raw `eval` badges. Internal names may stay in code/ids.
6. **No model-cost runs** in this work. QA uses the built-in checker, fixtures, and recorded motion. Do not Start Evaluations live.
7. **Do not restyle on the #13 branch.** Sequence: #13 merges → token/component PR on `main` → screen PRs → hosted consume.
8. **shadcn stays.** `web/components.json` is `base-nova` + Base UI + Lucide. Reuse components before adding new ones (`frontend-design`, `shadcn`, `clean-coder`). Do not introduce daisyUI or a second component kit.
9. **Keep the diff small per phase.** Tokens first. Do not rewrite routing, eval state, or the FastAPI contract as part of the look.
10. Docker image stays CLI (`check /pack`). UI is `skillgate ui` on the host.

---

## 1. What exists today (facts)

### 1.1 One tree, two modes (after #13)

`web/` is a Vite + React 19 + Tailwind 4 + shadcn (`base-nova`) app. `SKILLGATE_MODE` is `local` (default in this package) or `cloud`. `/api/status` returns `{mode, slots}`. Client stages (not URL routes): `home` · `repository` (Skills) · `eval` (Skill / Checks / Gate tabs) · `deploy` · `history` · `settings`. Pre-auth: Landing + Login (cloud only).

PR #13 copies this app into the public package and serves it from FastAPI on `127.0.0.1:8765`. Hosted still serves **its own** `web/dist`. The two trees already drift:

| Surface | PR #13 `web/` (this repo) | Hosted `skillgate-ai` after #158 |
| --- | --- | --- |
| Deploy | Local folder copy + git accordion; hosted copy still says `skillgate-ai serve` on Mini and prints `~/.cursor/skills` | Mac helper (pairing, devices, per-target Install), git publish in customer words, hides `/root` paths |
| History / Home | Slots hide them in local | Always on in cloud |
| Landing GitHub link | Points at public `skillgate` | Same file in hosted copy |

Revamp work happens **once**, in this repo’s `web/`, after #13. Hosted helper/git UI is pulled into shared `web/` as slots in the consume phase — not restyled twice.

### 1.2 Tokens today (`web/src/index.css`)

| Token | Today | Problem |
| --- | --- | --- |
| Type | `--font-sans` = Geist Variable; `--font-heading` = same | One face for chrome, Stamp, and landing. Not Inter, but still a single-sans “AI default.” No display pairing. Landing CSS module ignores Geist. |
| Color | Neutral light/dark shadcn. `--success` exists. Dark `--sidebar-primary: oklch(0.488 0.243 264.376)` | That sidebar primary is **purple** — the generic AI accent `frontend-design` forbids. Pass/fail are not a named pair with warn. Landing uses a parallel `#050506` / `#4ade80` / `#f87171` system. |
| Radius | `--radius: 0.75rem` → sm/md/lg/xl/2xl/3xl/4xl | Every card is `rounded-xl`. Landing CTAs are pills (`border-radius: 999px`). Uniform rounding. |
| Elevation | Cards: `ring-1 ring-foreground/10`, almost no shadow | Stacked identical cards. Stamp (the product) is not visually special. |
| Motion | `.eval-result-*` keyed animations; reduced-motion block | Gate motion is good and **must stay**. Almost no other intentional motion (nav, row open, Deploy unlock). |
| Spacing | Ad-hoc `gap-8` pages, `px-4 sm:px-6 lg:px-10` | No documented scale. |

`ThemeProvider` default is **light**. `d` toggles theme. Good; keep.

### 1.3 What Vignesh already likes (do not redesign)

Locked by OSS #7 / hosted #153 / #151 and visible in the prod screenshots:

1. **Checking hold** — Stamp stays mounted; copy is “Checking” + bar + `n/m`; min 700ms (`CHECKING_MIN_MS`).
2. **Slide** — Checking leaves left, result enters from right, 350ms (`EVAL_MOTION_MS`).
3. **Drawn mark** — SVG stroke of circle + check or X, 400ms, `role="img"` `Passed`/`Failed`.
4. **Rows-then-stamp** — Dataset rows appear queued immediately; Pass/Fail only when a task is `done`; suite metrics wait until Checking leaves.
5. **Table** — columns **Result | Check | What happened**; never a blank happened cell.
6. **Opened row** — five customer questions (Got the job done? Got it right? Followed the rules? Used the right evidence/actions? Delivered a good result?) plus Path.

Files to **preserve behavior** (restyle around, do not rewrite the state machine): `eval-result-shell.tsx`, `eval-result-mark.tsx`, `eval-stamp-body.tsx`, `checks-results-table.tsx`, `eval-row-state.ts`, `index.css` eval keyframes.

### 1.4 Known copy leftovers (from Vignesh + #156 follow-ups + this audit)

| Visible string | Where | Replace with |
| --- | --- | --- |
| `Power user: YAML` | Checks accordion | “Paste a check list” (or hide behind a plain “Import a list”) |
| `Harness` | Run config, Home table, skill Evals table | “Runs with” / Cursor · Codex · Claude · Auto |
| `Config changed` | History, skill Evals | “Settings changed from the last run” (already used on Gate) |
| Raw ISO on `title=` | History, Home, Skills, skill Evals, Deploy | `relativeTime` stays; tooltip is a **readable** datetime, not `2026-10-11T01:52:00+00:00` |
| Skill Evals rows don’t open | `skill-detail-page.tsx` | Same as History: click → Gate for that run |
| `pack hash` / `semver` | Landing dual band; skill Versions card | “Version” / “v1.2.3”; drop hash from customer chrome |
| `evidence_action_validity` | Must never leak; labels already mapped | Keep `CHECK_QUESTION_LABELS`; grep the built UI |
| `~/.cursor/skills` etc. | Skills description, Deploy hints (PR #13) | “Cursor’s skills folder” (hosted #158 already did this) |
| Absolute `/root/...` paths | Hosted Deploy before #158; still possible | `publicDestPath` rule: never show `/root`, `/tmp`, `/var`, `/app` |
| Badge `eval` / column `Evals` / `Last eval` / `Eval spend` | Skills, Home, skill detail | “Runs” / “Last run” / “Spend” |
| `GREEN` / `RED` | `GateBadge`, error panel, Gate page description | Open / Blocked, or Passed / Failed. Gate is not a traffic-light word for customers |
| `Browse all in Repository` | Evaluate Skill tab | “Browse all skills” |
| `skillgate-ai serve` on Mini | PR #13 Deploy hosted alert | Hosted #158 copy: “Install on your Mac” |
| `Cursor Agent harness` | Settings hint | “Runs checks in Cursor” |

Code/ids (`evalTab`, `#eval-result-stage`, `harnessPref`) may stay.

---

## 2. Design diagnosis (why it looks generic)

`frontend-design` forbids purple-on-white gradients, Inter everywhere, uniform rounded cards, emoji decoration. Current dashboard is the shadcn nova starter: near-white canvas, near-black type, Geist for everything, every panel a `rounded-xl` card with a hairline ring, lucide icons in `bg-muted` squares. Dark mode’s sidebar primary is literally purple (`oklch` hue 264). Landing is a second product: near-black, huge tracking-tight H1, pill buttons, screenshot frames. Prod Gate (screenshots) is a competent SaaS settings page with a stamp stuck in a card — the ritual is there, the frame is generic.

Skill Gate’s job is a **verdict**. The UI should feel like a ledger and a stamp, not a metrics dashboard that happens to have a checkmark.

**Direction (locked for Phase 2):** **Ink on paper.** Warm off-white sheet, near-black ink, one non-purple accent used rarely (rules / focus), and **pass / fail / warn as named ink**. Display serif **only** on Stamp headlines (Checking, Passed, Failed) and the landing H1. Geist stays for UI chrome (already loaded; it is not Inter). Tables are the primary surface (not cards wrapping tables wrapping cards). Radius tightens on data; the mark stays a circle. Landing and app share the same tokens.

Not: gradients, glass, neon, emoji, Inter, purple, pill-everything, new illustration system, a marketing-site rewrite of Evaluate.

---

## 3. Design tokens (Phase 2 writes these first)

Single source: `web/src/index.css` (`@theme inline` + `:root` + `.dark`). Landing `landing-page.module.css` must **consume** these variables (map `--sg-*` → `--background` / `--foreground` / `--success` / `--destructive`) instead of a private palette.

Do not invent extra colors in TSX. Semantic Tailwind only (`bg-background`, `text-success`, `text-destructive`, `bg-warning`). Matches shadcn skill + daisyUI semantic names without daisyUI CSS.

### 3.1 Type scale

| Token | Size / face | Use |
| --- | --- | --- |
| `--font-sans` | Geist Variable (keep) | Body, nav, tables, forms |
| `--font-heading` | Geist Variable, slightly tighter tracking | Page titles, card titles |
| `--font-display` | **Newsreader** or **Instrument Serif** (pick one in Phase 2; default **Newsreader**) | Stamp “Checking / Passed / Failed”, landing H1 only |
| `--font-mono` | Geist Mono or ui-monospace | Pairing codes, paste blocks, commands — never labels |

Scale (rem): `xs 0.75` · `sm 0.875` · `base 1` · `lg 1.125` · `xl 1.25` · `2xl 1.5` · `3xl 1.875` (page title) · `display 2.5–3rem` (Stamp + landing). Line-height 1.45 body, 1.15 display. Tabular nums on counts, times, pass rates.

Do **not** load Inter. Do not use display serif on table headers or buttons.

### 3.2 Color (light / dark)

Named roles, not raw utilities:

| Role | Light (intent) | Dark (intent) | Use |
| --- | --- | --- | --- |
| `--background` | Warm paper `oklch(0.985 0.008 90)` not pure white | Ink `oklch(0.16 0.01 90)` | App sheet |
| `--foreground` | Ink `oklch(0.18 0.02 60)` | Paper `oklch(0.97 0.01 90)` | Type |
| `--primary` | Same as ink (keep black buttons) | Paper | Primary actions |
| `--success` | Deep ink-green (not lime-400) | Brighter green on dark | Passed, open gate, PASS |
| `--destructive` | Vermillion (keep current-ish 27° hue) | Lighter red | Failed, blocked, FAIL |
| `--warning` | **New** amber/ochre | Amber | Unsure, settings-changed, stale |
| `--muted` / `--muted-foreground` | Warm gray | Warm gray | Secondary copy |
| `--border` | Hairline ink at 8–12% | Hairline paper at 10% | Tables, cards |
| `--sidebar` | Paper slightly cooler than sheet | Ink elevated | Nav |
| `--sidebar-primary` | **Ink, not purple** | **Ink/paper, not `264°` purple** | Active — fix the AI look |

Pass/fail/warn must meet **WCAG 2.2 AA** on paper and on ink (4.5:1 for text, 3:1 for 18px+ display). Stamp display green/red is large type — still check against paper. Do not encode Pass vs Fail by color alone: keep the word PASS/FAIL and the drawn mark.

Chart tokens stay grayscale; do not introduce a rainbow dashboard.

### 3.3 Spacing

`--space-1` … `--space-12` mapped to 4px grid: 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64. Page: `gap-8` (32) between sections, `gap-4` (16) inside a section. Main padding stays `px-4 sm:px-6 lg:px-10`. Sidebar `w-60`. Do not introduce a new layout grid library.

### 3.4 Radii

| Token | Value | Use |
| --- | --- | --- |
| `--radius` | **0.5rem** (down from 0.75) | Buttons, inputs |
| `--radius-sm` | 0.25rem | Table rows, chips, mosaic cells |
| `--radius-lg` | 0.75rem | Dialogs, sheets |
| `--radius-mark` | 999px | Stamp SVG only |

Cards lose the default `rounded-xl` sameness: data cards `rounded-lg`; Stamp card may stay slightly larger. Landing pills become `--radius` (not 999) so landing and app feel like one product. The **mark** stays a circle.

### 3.5 Elevation

| Level | Treatment |
| --- | --- |
| 0 sheet | Background only |
| 1 rule | `border` / `ring-1 ring-foreground/10` (tables, sidebar) |
| 2 paper | Card on muted well (empty states) |
| 3 stamp | Stamp column unchanged in z-index; **no drop-shadow theatre** |

No colored glows. No hover-lift on every card. Button `active:translate-y-px` stays.

### 3.6 Motion (keep Gate; name the rest)

Keep existing keyframes and timings. Document them as tokens so later work cannot “improve” them:

| Name | Value | Use |
| --- | --- | --- |
| `--motion-check-hold` | 700ms | Checking minimum |
| `--motion-slide` | 350ms cubic-bezier(0.22, 1, 0.36, 1) | Checking ↔ result |
| `--motion-mark` | 400ms linear | Stroke + scale |
| `--motion-bar` | 1.15s ease-in-out | Checking bar |
| `--motion-row` | 180ms | Open/close check details (new, height/opacity only) |
| `--motion-nav` | 120ms | Sidebar active background |

`prefers-reduced-motion: reduce` already covers Gate. Extend it to `--motion-row` and landing reveal (landing already skips IntersectionObserver animation).

Do not add confetti, bounce, or gradient wipes.

---

## 4. Component changes

Reuse shadcn primitives. Change tokens and a few wrappers; do not fork a new kit.

| Component | File | Change |
| --- | --- | --- |
| Tokens | `web/src/index.css` | §3. Landing CSS maps onto them |
| `GateBadge` | `chrome.tsx` | Labels **Open** / **Blocked** / **Pending**. Color via `--success` / `--destructive`. Drop `GREEN`/`RED` |
| `PageHeader` | `chrome.tsx` | Display vs heading roles; description stays `text-muted-foreground` |
| `Card` | `ui/card.tsx` | Tighter radius; optional `data-tone="stamp"` for the Gate stamp card (no extra shadow) |
| `Badge` | `ui/badge.tsx` | Add `success` / `warning` variants (semantic). Pass/Fail use these, not `secondary`+`text-success` |
| `Button` | `ui/button.tsx` | Keep variants. Disabled Deploy stays visually blocked (not just opacity — pair with Open/Blocked copy) |
| `Table` | `ui/table.tsx` | Default for Skills/History/Home. Checks results table may stay a native `<table>` (expanding rows) but **look** like the same type/spacing |
| `Alert` | `ui/alert.tsx` | Warning variant uses `--warning`. Copy: “Settings changed from the last run” |
| Checks table | `checks-results-table.tsx` | Row-open motion token; keep columns and five answers. PASS/FAIL stay words + color |
| Stamp body | `eval-stamp-body.tsx` | Display font on Checking/Passed/Failed only. Drop `RED` title on error panel |
| Sidebar | `app-sidebar.tsx` | No purple. Skills is default home in local. Hide cloud slots. Skill dock: Open/Blocked, not GREEN |
| Topbar | `app-topbar.tsx` | Fine. `⌘K` already. Search aliases: `eval` → Evaluate internally, user-facing placeholder stays “Search…” |
| Empty | `ui/empty.tsx` | Keep. Copy pass in screen phases |
| Landing | `landing-page.tsx` + module CSS | Same tokens; jargon pass; screenshots of **revamped** Gate after Phase D |
| Login | `login-page.tsx` | Same card language as app |
| Relative time | `time.ts` | Add `absoluteTime()` for tooltips |

**Do not add:** new chart library, new icon set, daisyUI, Framer Motion (CSS is enough), a second Stamp implementation.

**New files allowed (small):** `web/src/lib/copy.ts` for customer glossary used by grep tests; optional `web/src/components/dashboard/status-badge.tsx` if `GateBadge` + Pass/Fail share one helper. Prefer extending `GateBadge` / `Badge`.

---

## 5. Per-screen audit (both modes)

Legend: **L** = local `skillgate ui`; **C** = cloud hosted. Slot = hidden locally.

### 5.1 Landing (C only)

**Now:** Dark CSS-module page, “Evaluate. Gate. Deploy.”, Get started + Sign in with Vercel. Story bands. Dual band still says pack hash / semver. Footer “Open source on GitHub” → public `skillgate` (good in this tree). Hero shot is current Gate Fail.

**Problems:** Parallel palette; jargon; screenshots will be stale after revamp; pill CTAs vs app buttons; no skip-link; contrast of ghost Sign in on near-black is OK, primary is OK.

**After:** Same story, shared tokens, display serif on H1 only. Dual band: “Each version is recorded. Deploys and fails show in History.” Screenshot captions without `semver` / `pack hash`. CTA radius matches app. Hidden in local (AuthGate already skips).

### 5.2 Sign-in (C only)

**Now:** Centered card, mark, “Sign in to continue.”, allowlist / not-configured hints, SIWV button.

**Problems:** Generic rounded-2xl card; “allowlist” is internal if it leaks; `not_allowlisted` copy is already fairly plain.

**After:** Same layout, paper/ink tokens, warning/destructive alert. Copy: “This account isn’t invited yet.” when denied. Hidden in local.

### 5.3 Home (C slot `analyticsHome`; L hidden)

**Now:** KPI cards (Eval runs, Pass rate, Deployments, Eval spend), recent deploys, recent runs with **Harness** column, ISO hover, rows open if `run.id`. Empty: “No runs yet.”

**Problems:** SaaS dashboard aesthetic; “eval” in every label; Harness; ISO; four equal cards.

**After:** Keep as cloud analytics. Labels: Runs, Pass rate, Deploys, Spend. Column “Runs with” (Cursor/Codex/…). Tooltip readable date. Same empty CTA to Evaluate. Local: not shown; Skills is home.

### 5.4 Skills list (L + C)

**Now:** Table Skill / Gate / Evals / Versions / Last eval. Local description dumps `~/.cursor/skills`. Import button local-only. Gate GREEN/RED. Seed badge. Row click → skill page; Evaluate →.

**Problems:** Path jargon; `Evals`; GREEN; last-eval ISO; “Repository” leftover in Evaluate’s link; empty state mentions `skills/` path.

**After:** Columns Skill / Gate / Runs / Last run (drop Versions from the list — keep on the skill page). Gate Open/Blocked/Pending. Local blurb: “Skills in this project and in Cursor, Codex, and Claude.” Import: “Import from Cursor, Codex, Claude.” Empty: “Paste a skill file on Evaluate, or add a skill folder to this project.” Connect/import is this page’s local action (no separate route today — keep it here; do not add a wizard).

### 5.5 Connect / import (L; C N/A)

**Now:** `Import from agent folders` on Skills. No dedicated Connect screen. #12 recommended scan-on-start + Connect empty-state.

**Problems:** Button label is fine-ish; description still uses `~/.…`. No source chip (Cursor vs this project) on rows (`SkillPayload` may not show origin).

**After:** Same button, plain label. Empty-state primary action “Import from Cursor, Codex, Claude.” If origin is in the API, a quiet source word on the row — not a path. Do not add a setup wizard (#12 Settings-not-wizard lock).

### 5.6 Skill page / SKILL.md (L + C)

**Now:** Title + description, Evaluate / Deploy / View Dataset, mosaic (cloud), stats Last gate / Evals / Versions / Deploys, pack browser + SKILL.md, Evals table (Harness, Config changed, hash slice), Versions `semver` + Hash, Deployments.

**Problems:** Evals rows **do not open**; Harness; Config changed; semver + fingerprint copy; mosaic “No evals on…”; hashes in the version cell; many equal cards.

**After:** SKILL.md remains the center (pack browser). Stats: Last gate, Runs, Versions, Deploys. Evals table: When / Gate / Runs with / Settings / Version — **click opens Gate** (same `openHistoryRun` as History). Versions: Version / When (hash only in a details disclosure if needed for support — not a column). Mosaic stays a cloud slot; legend already uses words. Dataset viewer unchanged in behavior.

### 5.7 Evaluate — Skill / Checks / Dataset (L + C)

**Now:** Three tabs. Skill: pick list (8 of N), paste SKILL.md, zip. Checks: run-config **Harness**, fixture accordion, notices, check list, **Power user: YAML**, Run / Start Evaluations. Dataset dialog.

**Problems:** YAML label; Harness; “Start Evaluations” vs local “Run”; “Browse all in Repository”; missing-key banner mentions `CURSOR_API_KEY` / `codex login` (cloud); Generate checks is a slot (keep hidden locally); fixture copy is mostly plain.

**After:** Tabs stay. Primary local CTA remains **Run**; cloud may keep “Start” but not “Start Evaluations.” Run config legend: “Runs with” + Auto / Cursor / Codex / Claude. YAML: “Import a list” + customer placeholder without `suite:` jargon if possible (schema can stay in the box as an example, labeled “example list”). Generate stays `generateChecks` slot. Dataset: keep “View Dataset” (product word Vignesh uses).

### 5.8 Gate / results (L + C) — **preserve motion**

**Now:** Stamp + Metrics; Checking / Passed · 5/5 / Failed · 0/8; GREEN/Blocked chip; scored-by line; coverage; Pin as baseline; settings-changed alert (already plain); GitHub Actions: Not reported; Deploy button; Checks table with expandable five answers. Prod screenshots match this. Error panel title `RED`. Standalone Gate header: “RED blocks deploy. GREEN is the CI bar.”

**Problems:** GREEN/RED; “Last eval for…”; “Path” as a metric without a customer gloss (keep the word Path — it is in the five-answer lock, just don’t show raw step counts as the chip — already locked); Metrics card is a second equal card; historical run still shows raw run id + ISO in one alert.

**After:** Same layout and motion. Display serif on Checking/Passed/Failed. Badge Open/Blocked. Page chrome (if ever un-embedded) without GREEN/RED. Historical: “Earlier run, 11 Oct 2026” not uuid + ISO. Metrics stay; wait until stamp is visible (already). Table styling uses new type/spacing; **do not change column names or five questions.**

### 5.9 History (C slot `sharedHistory`; L pack-local if shown)

**Now:** Table When / Result / Skill / Config; Config changed badge; ISO `title`; Open; Pin as baseline. Sheet duplicate. Deploy rows don’t open (OK). Try-out labeled Single check.

**Problems:** Config changed; ISO; “eval” in sheet description (“that eval”).

**After:** “Settings changed from the last run”; readable tooltip; sheet: “Open a run to see what happened.” Rows that are runs still open Gate.

### 5.10 Deploy (L folders vs C helper / git)

**Now (PR #13):** Three equal cards Cursor/Codex/Claude with path hints; git accordion (slot); Mini/`serve` leftover; version line with hash slice.

**Now (hosted #158, screenshots):** “Install on your Mac”; connected device “Skill Gate box (Linux)” online dot; per-target Install; local CLI fallback; “Publish to your skills repo.” QA banner above.

**Problems:** PR #13 behind hosted; remaining GREEN/red in notes; hash in version line; online status is color-only (`bg-emerald-500` dot); pairing command is necessarily technical (OK) but must not show `/root`.

**After (shared UI):** One Deploy page, branched by slots + `local_available`:

- **L:** Install to Cursor / Codex / Claude (folder copy). No Mac pairing. No git unless `gitPublish` on (off locally).
- **C:** Mac helper block (`macHelper` slot) + git publish slot + “or install with the free CLI.” Device status: word **Online** / **Offline** plus the dot (already has the word in description — keep it, don’t rely on color). Hide absolute junk paths (`publicDestPath`).

Do not restyle hosted’s copy in the hosted repo; port #158 into this `web/` then restyle once.

### 5.11 Settings (L + C)

**Now:** Model keys; local `.env` vs cloud vault copy; hints “Cursor Agent harness”; QA-open sentence mentions “qa database.”

**Problems:** Harness; QA copy is for operators (keep the banner in `App.tsx`, not this paragraph); five identical fields.

**After:** Hints in customer verbs (“Runs checks in Cursor”, “Scores live checks”). QA-open sentence only when `auth_open_reason === "qa"` and shorter: “QA — keys save on the shared QA account, not production.” Structure can stay FieldGroup.

### 5.12 Chrome (both)

**Now:** Sidebar Skill Gate / Evaluate, Gate, Deploy; Home/History slotted; GitHub Action link if `ci.url`; docked skill + GREEN; version. Topbar search, theme, sign out (cloud), history icon (cloud). QA alert.

**Problems:** GREEN; “Evaluate, Gate, Deploy” subtitle is fine; GitHub Action is internal-ish but useful — keep, label “GitHub Action” is OK. Mobile sheet exists.

**After:** Open/Blocked on the dock. Local default stage already Skills (`repository`) in #13. Nav active uses sidebar accent, not purple primary.

### 5.13 Loading / error / empty (both)

**Now:** “Loading…” center; catalog errors; Empty primitives; missing-key destructive alert.

**After:** Same states, warning vs destructive as appropriate. Missing key is not a failure of the gate — consider `variant="warning"` so red is reserved for Failed/Blocked.

---

## 6. Accessibility checklist (every UI phase)

Phase 2+ PRs must not regress this. Gate table already has `tabIndex`, `aria-expanded`, `aria-controls`, Enter/Space.

- [ ] **Contrast** AA for ink/paper, success text on paper, destructive text on paper, muted on paper, dark mode pair.
- [ ] **Pass/fail not color-only** — word + mark + (table) PASS/FAIL.
- [ ] **Focus** visible (`ring`); no `outline-none` without a replacement (Button already uses `focus-visible:ring-3`).
- [ ] **Keyboard** — tabs, dialogs, check rows, sidebar (buttons), Deploy, theme toggle. `⌘K` / Ctrl+K.
- [ ] **Skip link** to `#main` (add `id` on `<main>` — today it has no id).
- [ ] **Landmarks** — one `nav` (sidebar), one `main`, banner (topbar). Landing already has `nav`/`main`/`footer`.
- [ ] **Dialogs** — Title required (shadcn rule). Dataset, promote, add-check already titled.
- [ ] **Live region** for Checking progress (`aria-live="polite"` on `#run-progress`) so screen readers hear n/m without focus move.
- [ ] **Reduced motion** — Gate + landing + new row-open.
- [ ] **Hit targets** — Deploy/Run `size="lg"`; icon buttons have `aria-label`.
- [ ] **Forms** — Field + Label (shadcn). Settings keys already.
- [ ] **Language** — `html lang="en"` already. Don’t leave `GREEN` as the only status (not a word).
- [ ] **Tooltips** — readable dates, not ISO; don’t rely on `title` alone for essential info.
- [ ] **Online dot** — text next to color.
- [ ] **QA banner** — not `aria-hidden`; it is a real warning.

No axe-only-in-CI requirement in the first token PR; add a Vitest/playwright smoke that Checking progress has `aria-live` in the Gate phase.

---

## 7. Phases that each ship

Each phase is a PR on a new branch off `main` **after #13 is merged** (except this docs PR). After each: OSS `check` 0/1 still works; hosted still serves **its** copy until the consume phase. No dark-season rewrite. `clean-coder`: no drive-by refactors.

### Phase 0 — this PR (docs)

`docs/plans/ui-revamp.md` + README pointer. No `web/` edits.

### Phase 1 — tokens + primitives (after #13)

**Ships a look without moving layout.**

- `web/src/index.css`: type, color (kill purple), warning, radii, motion CSS variables, reduced-motion extension.
- Load display font (Newsreader) next to Geist.
- `Badge` success/warning variants; `GateBadge` Open/Blocked; `time.absoluteTime`; Card radius.
- Landing CSS maps to tokens (may still look mostly the same).
- Vitest: GateBadge labels; grep test that built/bundled user strings in `web/src/components` do not contain `GREEN`, `Power user: YAML`, `pack hash`, `evidence_action_validity` **if those strings move in this PR**; otherwise the grep lands with the copy phase.
- **Do not** change eval state machines.

Hosted: still its own `web/`. Optional: cherry-pick token file later; better to wait for consume.

### Phase 2 — copy + chrome

Glossary pass on sidebar, topbar, PageHeader, Home labels, Skills columns, Evaluate YAML/Harness, Settings hints, Deploy PR #13 Mini leftover. `web/src/lib/copy.ts` + ESLint or Vitest grep for the deny-list in `web/src/**/*.tsx` (not tests). Skill Evals rows call `openHistoryRun`. Readable date tooltips.

### Phase 3 — Gate / Evaluate restyle (keep motion)

Stamp display font; metrics/card density; checks table spacing + row-open `--motion-row`; error panel without `RED`; live region. Screenshot refresh for landing **after** this phase. Record Checking → Failed and Checking → Passed (built-in checker, pdf twins) — **no live model**.

### Phase 4 — Skills, skill page, History, Home, Settings, empty/error

Paper/ink density: fewer nested cards around tables; mosaic unchanged logically. Local import empty-state.

### Phase 5 — Deploy slots + Mac helper in **this** `web/`

Port hosted #158 helper UI + `publicDestPath` + git customer copy into shared `web/`, gated by `macHelper` / `gitPublish` / `local_available`. Then apply tokens. Local still folder-copy cards. This may land with hosted consume if smaller as one PR — prefer **this repo first** so hosted deletes its Deploy page instead of restyling it.

### Phase 6 — Landing + sign-in

Jargon-free landing; new Gate screenshots; shared tokens; skip link. Cloud only.

### Phase 7 — Hosted consumes shared UI (`mode=cloud`)

See §8. Delete hosted dashboard TSX. Pin `skillgate-ai` wheel **or** build `web/` from this repo in the hosted Docker (open decision). QA/prod still work.

Do not start Phase 1 until #13 is on `main`. If #13 is still open, only this plan moves.

---

## 8. How hosted switches to the shared UI

Follows one-codebase §7 Phases 1–3. UI-specific:

1. **Freeze** new visual work on `skillgate-ai/web` (hotfixes only). Helper/git already on hosted `main` (#158) — port into public `web/` (Phase 5 above) before delete.
2. Public package ships `web/dist` in the wheel (#13 already plans this). Hosted Dockerfile.vercel today builds **its** `web/`. Change: `pip install skillgate-ai==pin` (or copy `web/` from the pin’s sdist) and serve that `web_static`. `SKILLGATE_MODE=cloud`. `/api/status.slots` all true that cloud implements.
3. Hosted Python keeps auth, vault, Neon, Jev, sandbox, helper pairing APIs. It must **not** contain `web/src/components/dashboard/eval-page.tsx` after consume. CI: fail if those paths exist (one-codebase Phase 3).
4. AuthGate, Landing, Login live in the **shared** tree, rendered only when `auth_required`. Local never sees them.
5. Until consume ships, expect **drift**. Do not “quickly restyle” hosted. Cherry-pick only production copy bugs.

Open decision (from #12, still open): hosted builds UI from the wheel vs a git submodule vs duplicating the Vite build in cloud CI against the pin. **Recommendation:** cloud CI installs the pinned wheel, copies `skillgate_ai/web_static` into the Function image. One artifact.

---

## 9. QA + recording (no model cost)

Never press live Start Evaluations / Run with Cursor/Codex/OpenAI keys for this work.

### Automated (every UI phase)

- `pnpm --dir web test` · `pnpm --dir web build`
- `python3 -m pytest` (unchanged engine)
- `skillgate check skills/pdf` exit 0; `skills/pdf-sabotaged` exit 1
- Vitest: Gate motion constants still 700/350/400; five-question order; `mode=local` hides sign-in/Home/History-cloud
- Grep (copy phase+): deny-list in `web/src/components/**/*.tsx`

### Live QA / recording (~3 min, built-in checker)

Record against `skillgate ui` (local) after #13 + token/Gate phases. Optional second clip of hosted QA **after consume**, still using a fixture skill that fails/passes without a paid model if possible.

1. Skills list → import copy (no secrets).
2. Open `pdf-sabotaged` → SKILL.md → **no auto-run**.
3. Run (built-in checker) → Checking hold → slide → drawn **Failed** → table Result | Check | What happened → expand a row → five answers.
4. Open `pdf` → Run → drawn **Passed** → Deploy button enabled → install into a temp Cursor skills dir (or skip install on camera).
5. Theme toggle; mobile sheet nav; keyboard expand-row.
6. Cloud-only (after consume, still no live model if possible): landing jargon check; sign-in page render (don’t need a real login on camera); Deploy page shows Mac helper empty state **without** `/root` paths.

Keep recordings free of keys and private hostnames. Prefer `docs/proof/` only if clean.

**Out of QA:** receipt-photo live Evaluate, Jev, Gateway, spend dashboards.

---

## 10. Files Phase 2+ will touch (not this PR)

| File | Why |
| --- | --- |
| `web/src/index.css` | Tokens, motion names, purple removal |
| `web/src/main.tsx` / `index.html` | Display font |
| `web/src/components/ui/badge.tsx` `card.tsx` `alert.tsx` | Variants |
| `web/src/components/dashboard/chrome.tsx` | GateBadge, headers |
| `web/src/components/dashboard/{eval-stamp-body,gate-page,checks-results-table,eval-page,repository-page,skill-detail-page,home-page,history-page,deploy-page,settings-page,app-sidebar}.tsx` | Screen phases |
| `web/src/components/marketing/landing-page.tsx` + `.module.css` | Token map + jargon |
| `web/src/lib/time.ts` `copy.ts` (new) | Tooltips, grep |
| Hosted consume PR (private repo) | Delete copied UI; pin wheel |

Risks: two UIs drift until consume; display font FOUC (preload); tightening radius looks “broken” next to old screenshots (refresh landing shots in Phase 6); Gate motion regressions (Vitest + recording). Mitigation: don’t edit `eval-result-shell.tsx` logic; CSS class names stay.

---

## 11. Out of scope

- Product code in **this** PR
- Pushing to `cursor/react-ui-local-mode-3b9f`
- Live model Evaluate / Jev / spend
- daisyUI as a dependency
- New routes, FastAPI contract, billing UI
- Rewriting eval/check state
- Flipping this GitHub repo public
- Vanilla `local_ui` deletion (owned by #13 follow-up)
- Changing five-question wording (already customer-plain)

---

## 12. This PR

Docs only:

- `docs/plans/ui-revamp.md` (this file)
- README pointer under Docs

No application code, no `web/` restyle, no hosted changes.
