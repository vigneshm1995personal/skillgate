# Custom judge checks — Implementation Plan

> **Phase 1 is this plan.** Phase 2 implements engine / schema / CLI / tests. Phase 3 implements the Checks editor **after PR #19 merges**. Do **not** write product code in this PR. Do **not** bump/publish PyPI. Do **not** merge until Vignesh says so.

**Goal:** Let the end user add, remove, and edit the questions Skill Gate asks when it scores a live check. Today every check is scored by the OpenAI Decisions judge (`gpt-6-luna`, `POST /v1/decisions`) answering five fixed Pass-lock questions plus Path, plus per-case expectations in `evals/cases.yaml` (`should_trigger`, `contains` / golden, `output_path`). Example: pdf 8/8 green, and the no-trigger `no-trigger-unrelated` case that should not pick pdf.

**Parents:** `main` @ `7a0ab4e` (0.5.0, #18). OpenAI judge plan [`openai-judge.md`](openai-judge.md). Product locks in [`0.5-decisions.md`](0.5-decisions.md). **PR #19** (`cursor/ui-revamp-tokens-df92`, “Full UI revamp: black and white…”) is **open, draft, unmerged**. UI work in this feature **lands after #19**, not in parallel.

**Hosted:** private `vigneshm1995personal/skillgate-ai` keeps pinning the public `skillgate-ai` wheel. One codebase: the resolver, Pass/warn rule, and React Checks editor live in OSS. Hosted does not fork a second question bank.

Inspected OSS tree: `main` @ `7a0ab4e`. PyPI dist **`skillgate-ai` 0.5.0**. CLI **`skillgate`**.

---

## 0. Locked product decisions

These are not open questions. If a later change fights one of these, the lock wins.

1. **One pack on disk** + `skillgate check` exit **0 or 1** (or **2** with no live key). No Skill Gate account.
2. **Missing `judge:` = today’s bank.** Existing packs (`skills/pdf`, `skills/pdf-sabotaged`, user packs on schema 1) keep the five Pass-lock questions + Path, the same ordinals, the same Pass lock, the same no-trigger det-owns rule. Schema stays **1**. `judge:` is additive.
3. **Low-confidence rule stays:** a Pass-lock / blocking `choice` or `score` answer that would Pass, with confidence missing or `< 0.5`, **keeps Pass** and warns: *The judge wasn't very sure about this one.* Never fails the check. Never blocks Deploy. Never changes exit 0/1. Default `SKILLGATE_JUDGE_MIN_CONFIDENCE=0.5` remains. Predicate answers have no `confidence` field (official Decisions); do not invent one.
4. **Trigger expectation and expected output stay first-class case fields**, not judge questions. `should_trigger`, `contains` / golden, `output_path` remain in `evals/cases.yaml` and the Checks editor. The new `judge:` block is the LLM questions only.
5. **`on_fail: block` vs `on_fail: warn`.** Block fails the check (`passed=false`, exit 1) → Deploy refuses (latest check did not pass). Warn never flips `passed`. Deploy already keys off `passed`; do not add a second Deploy gate. Path stays warn by default. The five current Pass-lock questions stay block by default.
6. **No-trigger cases still keep det ownership** (`expect_skill is None`). Custom questions on those cases are evidence only, unless the case sets `judge.score_no_trigger: true` (off by default).
7. **Customer copy is plain words.** UI/CLI: “Got the job done?”, “Yes/no”, “Pick one”, “Score”, “Fail the check”, “Warn only”. Do not show `task_completion`, Decisions, Jev, `gpt-6-luna`, or schema keys in chrome. `--json` may keep ids.
8. **Hosted reuses this code.** Private TypeSafe/Jev remains the hosted default **only when the resolved bank is the built-in one**. A pack with a custom `judge:` uses the OSS `OutcomeJudge` (Decisions) from the wheel. Do not copy `judge_bank` into the private repo.
9. **UI after #19.** Phase 2 may ship schema + CLI + engine with no React editor. Phase 3 rebases onto merged #19 (black-and-white tokens) and extends the existing Checks editor. Do not restyle `web/` against `main` while #19 is open.
10. **Decisions remains the scoring API.** Custom questions still go in one `questions[]` on `POST /v1/decisions`. Responses + Structured Outputs stays the operator fallback (`SKILLGATE_JUDGE_BACKEND=responses`) and the Fail why-call. Generate that schema from the resolved bank; do not keep a hardcoded six-field enum once questions are custom.

---

## 1. What exists today (facts, not hunches)

### 1.1 Scoring stack

| Piece | Path | Fact |
| --- | --- | --- |
| Fixed bank | `src/skillgate_ai/judge_bank.py` | `CHECK_CELL_ORDER` (5) + `SOFT_CELL_ORDER` (`path_efficiency`). All type `choice`. `PASS_LOCK` is a frozenset of allowed ordinals per key. `DEFAULT_MIN_CONFIDENCE = 0.5`. |
| Pass lock | `outcome_verdict` | All five must be in-lock. Path is ignored. Missing/unknown enum → `UNUSABLE_ANSWER`, fail closed. |
| Low confidence | `low_confidence_warnings` | Only if the five would Pass. Decisions backend only. Warning list; `passed` unchanged. |
| HTTP | `judge_openai.py` | Default `DecisionsBackend` builds `decisions_questions()`. Fallback `StructuredOutputsBackend` uses `structured_output_schema()`. |
| Engine | `engine._live_verdict` | Skip → det owns. Error → fail closed. `expect_skill is None` → det owns, judge stored as evidence. Completed bool `passed` overrides det. Output mismatch still fails. |
| Gate | `gate.run_check` | `resolve_judge` → `run_eval(..., judge=)`. No OpenAI/gateway key → `SkipJudge`; det scorers own red/green. |
| Deploy | `deploy.require_passing_check` | Needs a **passing** latest history row. Warnings do not matter. `--force` only overrides a red latest, never never-checked. |
| Pack SoR | `evals/cases.yaml` schema 1 | `PackCase`: `id`, `status`, `prompt`, `should_trigger`, `input`, `golden`, `contains`, `min_pages`, `budgets`. **No `judge` field.** |
| Fingerprint | `PACK_FINGERPRINT_FIELDS` | `id`, `prompt`, `should_trigger`, `input`, `golden`, `budgets`. Changing questions today would **not** invalidate Deploy trust. |
| CLI | `cli.py` | `keys` is a Typer sub-app (`show` pattern). No `judge` command. `check` has no question flags. |
| Seed packs | `skills/pdf/evals/cases.yaml` | 8 pinned cases. `no-trigger-unrelated`: `should_trigger: false`, `golden: null`. |

Built-in questions (user-facing labels → Pass ordinals):

| Key | Ask | Pass | Default `on_fail` |
| --- | --- | --- | --- |
| `task_completion` | Got the job done? | Fully completed | block |
| `correctness` | Got it right? | Correct | block |
| `instruction_adherence` | Followed the rules? | Fully followed | block |
| `evidence_action_validity` | Used the right evidence/actions? | Fully supported **or** N/A | block |
| `result_quality` | Delivered a good result? | Clear and complete **or** Mostly good | block |
| `path_efficiency` | Path | (not in lock; Efficient / Acceptable / Looping / Wasteful) | warn |

### 1.2 Already user-configurable (keep; do not move into `judge:`)

These stay on the case, edited in the Checks editor today (`check-list.tsx`):

- **Trigger expectation** — checkbox “This should trigger the skill” → `should_trigger`.
- **Expected output** — Expected / Output file / fixtures → `contains`, `golden`, `output_path`.
- **Budgets** — optional token/step caps; a set number **blocks Deploy** if exceeded (`metrics.py`). Independent of the judge.

### 1.3 UI facts and PR #19

- Primary UI is React `web/`, served by `skillgate ui` from packaged `web_static`.
- Checks editor: `web/src/components/dashboard/check-list.tsx` + `add-check-dialog.tsx` on the skill/eval Checks tab (`eval-page.tsx`).
- Tokens today on `main` still include cream/oxblood leftovers in some screens; **#19 restyles the whole tree to black and white** (white/near-black light, black/white dark, chroma only for Pass/Fail, Geist). Head `e5a2432`, draft, mergeable, **do not merge from this work**.
- Vanilla `local_ui/static/` is the older wizard. Do not add a second Checks editor there. Phase 3 targets React only.
- `frontend-design`: reuse Field / Checkbox / Button / Accordion; no new palette; no purple-on-white, no extra radii.

### 1.4 Decisions API limits (verified vs labeled)

Official [Decisions guide](https://developers.openai.com/api/docs/guides/decisions) (re-fetched 2026-10-11):

- `POST /v1/decisions`, model **`gpt-6-luna` only**.
- Question types: **`predicate` | `choice` | `score`**.
- Names must be unique; echoed on answers.
- `predicate` → `probability` (0–1). **No `confidence` in the official predicate excerpt.**
- `choice` → `choice`, `probabilities[]`, `confidence`.
- `score` → weighted average of **level indices starting at 0** (can fall between levels), `probabilities[]`, `confidence`. Adjacent levels must have distinct criteria. Use `choice` when you need one named category.
- Independent questions share one `input`.

**Not on that guide page (do not cite as OpenAI product copy):** a published per-request question cap. OpenAPI + downstream docs (pydantic-ai `openai_decisions`, Vercel AI Gateway Decisions) state:

| Limit | Value | Source |
| --- | --- | --- |
| Questions per request | **200** (201 → HTTP 400) | OpenAPI `DecisionRequest.questions.maxItems` |
| `choice` options | **1–255** | Gateway + OpenAPI |
| `score` levels | **2–10** | Gateway + OpenAPI |

**Product cap (ours, not OpenAI’s):** at most **20** questions per resolved check (built-in is 6). Keeps the UI readable and stays far under 200. Over 20 or over API hard limits → friendly validation error **before** HTTP. If OpenAI still returns 400, fail closed with the existing “OpenAI rejected this scoring request.”

---

## 2. What becomes user-configurable

| Lever | Scope | Default if omitted |
| --- | --- | --- |
| Add / remove / edit questions | Pack `judge.questions` and per-case override | Built-in six |
| Question type | Per question: `predicate` / `choice` / `score` | `choice` (built-in) |
| Ask text + criteria | Per question `ask` + choice/level descriptions | Today’s labels/criteria |
| Pass threshold | `choice`: which values Pass; `predicate`: min probability; `score`: min (or max) numeric score | Today’s `PASS_LOCK`; predicate `>= 0.5`; score documented per question |
| Fail vs warn | Per question `on_fail: block \| warn` | Five block, Path warn |
| Low-confidence cutoff | Pack/project `min_confidence` | `0.5`; behavior locked (Pass + warning) |
| Trigger expectation | Case `should_trigger` | `true` |
| Expected output | Case `golden` / `contains` / `output_path` | none (required to pin a should-trigger completion check) |
| Score no-trigger with LLM | Case `judge.score_no_trigger` | `false` (det owns) |

Not configurable in v1 (out of scope): swapping `gpt-6-luna`, changing the why-call, turning low-confidence into a Fail, averaging questions, free-form prose questions, hosted-only question types.

---

## 3. Where config lives

### 3.1 Precedence (highest last)

1. Built-in bank in `judge_bank.py` (code).
2. Project file **`skillgate.yaml`** at the workspace root (next to `skills/`). Optional. **Not** `{project}/.skillgate/` — that directory is gitignored because of keys.
3. Pack **`evals/cases.yaml`** top-level `judge:`.
4. Per-case **`cases[].judge:`**.

Resolved bank is what Decisions sees. Save the resolved snapshot on `tasks[].judge.questions` (already a dict today) so history is self-describing.

### 3.2 Schema 1 additive shape

Keep `schema: 1`. Unknown keys already fail pydantic validation — new fields must be declared on `CasePack` / `PackCase`.

```yaml
schema: 1
skill: pdf
judge:
  min_confidence: 0.5
  questions:
    - id: task_completion
      type: choice
      ask: Got the job done?
      on_fail: block
      choices:
        - value: Fully completed
          description: The requested work is fully done.
          pass: true
        - value: Partially completed
          description: Some of the requested work is done but incomplete.
          pass: false
        - value: Not completed
          description: The requested work was not done.
          pass: false
    - id: path_efficiency
      type: choice
      ask: Path
      on_fail: warn
      # ...
cases:
  - id: extract-hello
    prompt: Extract the text from hello.pdf and save it to output/extracted.txt
    should_trigger: true
    golden:
      output_path: output/extracted.txt
      path: evals/goldens/extract-hello.txt
      kind: text
    contains:
      - Hello Skill Gate
    # omit judge: → pack/project/built-in
  - id: no-trigger-unrelated
    prompt: Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.
    should_trigger: false
    golden: null
  - id: extract-invoice
    # per-case replace (full list). Overlay-by-id is rejected: two merge rules confuse authors.
    judge:
      questions:
        - id: numbers_match
          type: predicate
          ask: Do the invoice totals in the output match the input PDF?
          on_fail: block
          pass_if: { gte: 0.8 }
```

**Replace, do not overlay.** If `judge.questions` is present at a layer, it is the full list for that layer. The UI starts from the parent list so add/remove/edit is still one save. Empty `questions: []` means “no LLM questions; det scorers only” for that layer.

`skillgate.yaml` (project):

```yaml
judge:
  min_confidence: 0.5
  questions: []   # omit questions to keep the built-in bank; set min_confidence only if needed
```

Dump code (`_dump_pack`) omits empty `judge:` so seed packs stay byte-stable unless the user opts in.

### 3.3 Per-question fields

| YAML | Plain words | Rules |
| --- | --- | --- |
| `id` | (hidden; slug) | `^[a-z][a-z0-9_]*$`, unique in the list, ≤ 64 chars |
| `type` | Yes/no · Pick one · Score | `predicate` \| `choice` \| `score` |
| `ask` | The question | non-empty, ≤ 500 chars; this is Decisions `instructions` |
| `on_fail` | Fail the check · Warn only | default `block` except built-in Path = `warn` |
| `choices` | Options | required for `choice`; 1–255; ≥1 with `pass: true` unless `on_fail: warn` |
| `levels` | Score levels, lowest first | required for `score`; 2–10; ordered |
| `pass_if` | Pass when | `predicate`: `{gte: 0..1}` default `0.5`. `score`: `{gte: number}` (index scale) or `{lte: number}`. `choice`: use `pass:` on values, not `pass_if` |
| `include_when` | (advanced, optional) | `path_recorded` for Path-like questions. Omit = always. Built-in Path keeps today’s skip when no path. |

### 3.4 Fingerprint and Deploy

Add resolved `judge` (questions ids, types, pass sets, thresholds, `on_fail`) to `PACK_FINGERPRINT_FIELDS` / `pack_fingerprint`. Editing questions is a skill change: latest green history no longer matches → “This skill changed since it passed. Run the checks again, then install.” Same pattern as budgets.

---

## 4. Engine changes (Phase 2)

### 4.1 New module `skillgate_ai/judge_spec.py`

Load / validate / merge / resolve. No HTTP. Shared with hosted.

- `DEFAULT_SPEC` built from current `judge_bank` constants (single source; do not duplicate ordinals).
- `resolve_judge_spec(*, project, pack, case) -> ResolvedJudgeSpec`
- `to_decisions_questions(spec, *, include_path: bool) -> list[dict]`
- `to_structured_schema(spec, *, include_path: bool) -> dict`
- `verdict(spec, answers) -> (passed: bool, reasons: list[str], warnings: list[str])`

Generalize today’s `outcome_verdict` / `unusable_answers` / `low_confidence_warnings` to walk `spec.questions` instead of `CHECK_CELL_ORDER`. Keep those names as wrappers around the built-in spec so existing tests stay meaningful.

### 4.2 Answer handling by type

| Type | Unusable (fail closed) | Pass? | Low-confidence warning |
| --- | --- | --- | --- |
| `choice` | missing / not in values | `choice` in `pass: true` set | yes, if would Pass and confidence `< min` |
| `predicate` | missing / non-numeric probability | `probability >= pass_if.gte` | **no** (no official confidence) |
| `score` | missing / non-numeric | `score` vs `pass_if` | yes, if would Pass and confidence `< min` |

Unusable **blocking** question → check Fail (`UNUSABLE_ANSWER` / per-question plain reason). Unusable **warn** question → warning, check can still Pass.

`on_fail: warn` miss → append warning (“Path was Wasteful”), do not set `passed=false`.

### 4.3 Call chain

```
load_case_pack
  → resolve_judge_spec (project + pack + case)
      → OutcomeJudge.judge(..., spec=)
          → backend.evaluate(..., questions=from spec)
          → verdict(spec, answers)
      → _live_verdict (unchanged skip / error / no-trigger / mismatch)
```

`SkipJudge` ignores spec. No key → det only, as today.

### 4.4 Report / CLI / history

- `tasks[].judge.cells` already keyed by id + `{label, choice, reason, confidence}`. Add `type`, `on_fail`, and for predicate/score the numeric value (`probability` / `score`).
- CLI `format_cli`: blocking misses stay Fail reasons; warn misses print as warnings (Path already does this in spirit).
- Fail why-call unchanged (Responses, after a real Fail, not after warn-only).

---

## 5. CLI

Typer sub-app, same shape as `keys`:

```
skillgate judge show [PACK] [--case ID]
skillgate judge reset [PACK]
```

| Command | Behavior |
| --- | --- |
| `show` | Resolve and print the bank in plain words (ask, type, pass bar, Fail vs warn). `--json` dumps the spec. Invalid YAML → exit 2, friendly error. Default pack: cwd if it is a skill folder. |
| `reset` | Remove pack-level `judge:` so the built-in bank returns. Does not rewrite per-case `judge:` unless `--all-cases`. Prints “Using Skill Gate’s default questions.” |

**No interactive TUI `edit`.** Authors edit YAML or (Phase 3) the Checks editor. `show` is the validator. Optional later: `skillgate judge set --from FILE` if YAML-in-YAML is painful; not v1.

`skillgate check` reads the resolved spec automatically. **No** `--questions` flag (easy to desync from the pack).

`skillgate --help` lists `judge`.

---

## 6. Validation and friendly errors

Reuse `SuiteError` + `friendly_validation_error` (`errors.py`). Never pydantic.dev URLs, never tracebacks as primary UX. Exit **2** for author errors (bad YAML), exit **1** for a scored Fail.

| Mistake | Message (plain) |
| --- | --- |
| `type: ranking` | `Question {id}: type must be yes/no, pick one, or score.` |
| `choice` with 0 options | `Question {id}: add at least one option.` |
| `choice` with 256 options | `Question {id}: pick-one questions can have at most 255 options.` |
| `score` with 1 level | `Question {id}: a score needs between 2 and 10 levels.` |
| Duplicate `id` | `Two questions use the same id ({id}). Rename one.` |
| 21 questions | `A check can ask at most 20 scoring questions.` |
| `choice` with no `pass: true` and `on_fail: block` | `Question {id}: mark at least one option as a Pass, or set it to warn only.` |
| predicate `pass_if.gte: 1.5` | `Question {id}: yes/no Pass bar must be between 0 and 1.` |
| schema 2 | unchanged: `This case pack uses schema 2; Skill Gate supports schema 1.` |
| unknown key under `judge` | `Case pack is invalid: …` (existing pydantic loc labeling; extend `_loc_label` for `judge` / `questions`) |

`test_friendly_errors.py` style: loc includes `case {id} (judge)` when nested under a case.

---

## 7. Backward compatibility

| Pack | Result after Phase 2 |
| --- | --- |
| `skills/pdf` (no `judge:`) | Identical six questions, identical Pass lock, 8/8 contract unchanged |
| `skills/pdf-sabotaged` | Unchanged red twin |
| User schema-1 packs | Load as today |
| History JSONL | Additive fields; old rows still render |
| `SkipJudge` / no OpenAI key | Det scorers unchanged |
| Docker `CMD check /pack` | Unchanged; keyless still exit 2 |
| Responses fallback | Built-in spec still emits today’s enum schema; custom spec emits a generated schema |

Do **not** rewrite seed `cases.yaml` in Phase 2. Reset-to-defaults in the UI writes “no `judge:` key”, not a dumped copy of the bank.

---

## 8. UI (Phase 3 — after PR #19)

**Do not start this while #19 is open.** Rebase onto merged #19 (or merge `origin/main` once #19 is in). One `web/` tree for local and hosted.

### 8.1 Where

Skill page → Checks tab → each check card (`CheckList`). Add a **Scoring questions** accordion under Expected / Output / budgets (same Field pattern as token budget). Pack-level defaults: a **Default scoring questions** accordion above the list (skill-wide `judge:`).

Do not add a new route or Settings page for this.

### 8.2 Copy and controls (plain words, B&W)

- Heading: “Scoring questions”
- Description: “These are the questions Skill Gate asks after a live run. Fail the check blocks Install. Warn only still Passes.”
- Button: “Use Skill Gate defaults” → delete custom `judge:` at that layer.
- Per question: ask (textarea), type (Yes/no · Pick one · Score), Fail the check / Warn only (checkbox or two-option control using existing tokens, not a new color).
- Pick one: list of option value + description + “This option is a Pass”.
- Score: ordered levels + “Pass when score is at least / at most”.
- Yes/no: “Pass when yes-probability is at least” (0–1).
- Add question / Remove. Disable Add at 20.
- Trigger checkbox and Expected fields stay exactly where they are.

### 8.3 Design (frontend-design + #19)

- Follow `web/src/index.css` tokens from **#19**: white/near-black, black primary buttons, gray borders, Geist, chroma only on Pass/Fail badges.
- Reuse `Field`, `FieldLabel`, `FieldDescription`, `Checkbox`, `Input`, `Textarea`, `Button`, `Accordion`, `Badge`.
- No new radius, no gradients, no emoji, no Inter.
- Keyboard and focus states from existing Field/Button. Muted text stays ≥ 4.5:1 (`oklch(0.32)` on #19).
- Checking → slide → drawn Passed/Failed **unchanged** (700 / 350 / 400). Extra cells just render as more answer chips in the result panel (`eval-result-mark` / cells list).

### 8.4 API

Pin/save path already writes `evals/cases.yaml` (`POST /api/evals/pin`, `pin_checks`). Extend `Check` in `web/src/lib/types.ts` with optional `judge`. `checks_from_pack` / `_case_from_check` round-trip the block. `GET` skill payload includes pack-level `judge` + project defaults for the editor’s “inherited” hint.

Hosted: same React, `status.mode === "cloud"`. No `hostedJudge` slot required for editing questions; scoring still uses the wheel.

---

## 9. Hosted app (one codebase)

Private follow-up after OSS Phase 2 is on PyPI (or a git pin):

1. Pin `skillgate-ai` with `judge_spec`.
2. Import `resolve_judge_spec` + `verdict` from the wheel. Delete any private copy of ordinals.
3. `resolve_judge` hosted: if resolved spec **equals** the built-in bank → keep TypeSafe/Jev as today. If custom → OSS `OutcomeJudge` (user/gateway key, Decisions).
4. Same `web/` Checks editor; hosted does not add a second form.
5. This Phase 1 PR does **not** touch the private repo.

---

## 10. Files (Phase 2 vs Phase 3)

### Phase 2 — create

| Path | Why |
| --- | --- |
| `src/skillgate_ai/judge_spec.py` | Resolve / validate / Decisions payload / verdict |
| `tests/test_judge_spec.py` | Merge, types, thresholds, block vs warn, low-confidence, limits, empty questions |
| `tests/test_judge_cli.py` | `show` / `reset`, friendly errors, help |

### Phase 2 — change

| Path | Why |
| --- | --- |
| `judge_bank.py` | Keep constants as the built-in spec; verdict helpers delegate to `judge_spec` |
| `judge_openai.py` | Questions/schema from spec; predicate/score answer rows |
| `judge.py` / `engine.py` / `gate.py` | Pass resolved spec into the judge |
| `case_pack.py` | `judge` on `CasePack` and `PackCase`; fingerprint; dump omits empty; `checks_from_pack` |
| `cli.py` | `judge` Typer group |
| `errors.py` | `judge` loc labels |
| `report.py` | Extra cell types; warn-only lines |
| `docs/pack.md`, `docs/openai-judge.md`, `README.md` | Schema + CLI + “defaults if omitted” |
| `tests/test_judge_bank.py`, `test_judge_openai.py`, `test_case_pack_cli.py`, `test_friendly_errors.py`, `test_eval_config.py` | Spec-driven requests; fingerprint includes judge |

### Phase 2 — do not change

Docker `ENTRYPOINT`/`CMD`, seed `cases.yaml` contents, Checking motion, `web/` (wait for #19), private hosted repo, PyPI version (bump on the implementation PR if the schema is public — **0.5.0 → 0.6.0** because custom questions are a feature; this plan PR does not bump).

### Phase 3 — change (after #19)

`web/src/components/dashboard/check-list.tsx`, `add-check-dialog.tsx`, `eval-page.tsx`, `web/src/lib/types.ts`, `web/src/lib/case-pack.ts`, matching vitest files, result-cell rendering. Rebuild `web_static` the way #19 does (CI fails if git tree ≠ fresh `pnpm build`).

---

## 11. Test plan (TDD — Phase 2)

Write failing tests first; never weaken.

1. **Default bank** — pack without `judge:` → `decisions_questions()` identical to today (names, ordinals, Path optional).
2. **Replace at pack** — custom two-question list is what HTTP sends; built-in keys absent.
3. **Replace at case** — one case differs; siblings keep pack/default.
4. **Project `skillgate.yaml`** — applies when pack omits `judge:`; pack wins when present.
5. **choice Pass lock** — user `pass: true` set; unknown choice fail closed.
6. **predicate** — `probability >= 0.8` Pass; `0.4` Fail if block; warn if `on_fail: warn`.
7. **score** — `gte` / `lte`; between-level float (1.1) vs threshold.
8. **Low confidence** — blocking choice Pass + `confidence: 0.2` → Pass + warning. Predicate never warns on confidence. Warn-only miss does not add the low-confidence sentence.
9. **No-trigger** — custom blocking Fail does **not** override det Pass unless `score_no_trigger: true`.
10. **Limits** — 21 questions, 256 choices, 11 levels, 1 score level → SuiteError, no HTTP.
11. **Fingerprint** — changing `ask` or `on_fail` changes `pack_fingerprint`.
12. **Dump** — default pack YAML has no `judge:` key.
13. **CLI** — `judge show skills/pdf` prints the five asks + Path; `judge reset` is a no-op on seed; invalid type exit 2.
14. **Friendly errors** — no pydantic URL; mentions `case extract-hello`.
15. **Responses fallback** — generated `json_schema` matches the custom spec, `strict: true`.
16. **Existing** — `tests/test_judge_bank.py`, `test_judge_openai.py`, pdf/sabotaged contracts, `test_oss_surface.py` still green.
17. Full CI locally before push (see §13): pytest, pnpm test, gate keyless exit 2, web-build, oss-surface, docker.

Phase 3 tests: vitest for add/remove/edit, Fail vs warn label, reset-to-defaults, 20-cap, round-trip pin API. Browser pass on Checks editor (desktop + a narrow viewport) after #19 tokens.

---

## 12. Risks

| Item | Status | Mitigation |
| --- | --- | --- |
| PR #19 file overlap on `web/` | Fact; 139 files | Phase 3 after merge; Phase 2 has no `web/` diff |
| Hosted Jev vs custom questions | Fact: Jev is the fixed bank | Custom → OSS Decisions; built-in → Jev |
| Schema 1 vs a v2 bump | Additive `judge:` is enough | Stay on 1 so old packs load |
| `.skillgate/` for project defaults | Would be gitignored | Use committed `skillgate.yaml` |
| Overlay-by-id merge bugs | Hunch | Replace-only lists |
| `score` between levels vs Pass chip | Official: score can be 1.1 | Threshold on the float; chip shows the number + nearest label |
| 200 cap unused | Product 20 | Document both |
| Fingerprint invalidates old greens | Intended | Same as budgets; copy already exists |
| Seed YAML churn | Avoid | Do not dump defaults into `skills/pdf` |
| Responses schema explosion | Custom enums | Generate; keep `additionalProperties: false` and all required |

---

## 13. Implementation order

1. **This PR (Phase 1):** this document only. Draft PR. Stop.
2. **Phase 2a:** `judge_spec` + tests for default ≡ today’s bank.
3. **Phase 2b:** pydantic on `CasePack`/`PackCase`, fingerprint, friendly errors, dump-omit.
4. **Phase 2c:** wire `OutcomeJudge` + engine; predicate/score; block vs warn; no-trigger lock.
5. **Phase 2d:** `skillgate judge show/reset`; docs (`pack.md`, `openai-judge.md`).
6. **Phase 2e:** full CI; Thermos; implementation PR (not this one). Version **0.6.0** on that PR.
7. **Phase 3:** wait for #19; rebase; Checks editor + vitest + `web_static`; browser verify.
8. **Hosted follow-up:** pin wheel; Jev only for built-in spec.

---

## 14. Out of scope (this PR and v1)

- Implementing any of the above in this branch
- Merging or rebasing onto PR #19
- Changing seed pdf cases
- Ambient OpenAI keys
- Making low-confidence a Fail
- Per-question model / temperature
- Marketplace / hosted billing
- Vanilla `local_ui` Checks editor
- Private `skillgate-ai` repo edits

---

## 15. This PR

Plan only: `docs/plans/custom-judge-checks.md`. Base `main` (0.5.0). Draft. No code, no version bump, no UI restyle.
