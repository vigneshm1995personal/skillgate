# Custom judge checks — Implementation Plan

> **Phase 1 is this plan.** Phase 2 implements engine / schema / CLI / providers / tests. Phase 3 implements Settings + the Checks editor **after PR #19 merges**. Do **not** write product code in this PR. Do **not** bump/publish PyPI. Do **not** merge until Vignesh says so.
>
> **Scope change (Vignesh, 2026-10-11):** (1) bring-your-own judge **provider** (OpenAI Decisions, Jev, AWS, OpenAI-compatible / other) with an explicit key — never ambient env. (2) Custom checks and judge questions are **added on top of** Skill Gate built-ins; they do not replace them.

**Goal:** Let the end user (a) pick who scores live checks, with their own key, and (b) add extra checks and extra scoring questions **alongside** the built-ins. Today every live check is scored by OpenAI Decisions (`gpt-6-luna`, `POST /v1/decisions`) answering five fixed Pass-lock questions plus Path, plus per-case expectations in `evals/cases.yaml`. Example: pdf **8/8** green, including `no-trigger-unrelated` (should not pick pdf).

**Parents:** `main` @ `7a0ab4e` (0.5.0, #18). OpenAI judge plan [`openai-judge.md`](openai-judge.md). Product locks in [`0.5-decisions.md`](0.5-decisions.md). **PR #19** (`cursor/ui-revamp-tokens-df92`) is **open, draft, unmerged**. UI work **lands after #19**.

**Hosted:** private `vigneshm1995personal/skillgate-ai` pins the public wheel. **One codebase:** provider interface, question resolver, and React Settings/Checks editor live in OSS `web/` + `skillgate_ai`. Hosted does not fork a second bank or a second provider stack.

Inspected OSS tree: `main` @ `7a0ab4e`. PyPI **`skillgate-ai` 0.5.0**. CLI **`skillgate`**.

---

## Open questions for Vignesh

Answer these before Phase 2 starts. Recommendations are in *italics*.

1. **Can built-ins be disabled?** *Recommend: cannot delete. Built-in judge questions can be marked **Warn only** (still asked, never fail the check / never block Deploy). Built-in pack cases (pdf’s 8, including no-trigger) cannot be removed from that pack; users only **add** cases. On a skill the user created, every case is theirs and can be deleted.* Confirm or pick another rule (e.g. allow hiding a built-in question entirely).
2. **Jev + extra questions.** Hosted Jev today scores the **fixed six cells**. If Jev’s public API cannot take arbitrary extra questions: *fail the extras with a plain message (“Jev scores Skill Gate’s built-in questions only. Pick OpenAI or another provider for extra questions.”) and still score the six.* Or refuse the whole run. Which?
3. **Jev customer name.** Settings/CLI: **Jev** vs **TypeSafe**. OSS UI currently treats `jev` as internal jargon in the vanilla wizard tests. *Recommend the Settings option is “Jev” once it is a user-chosen provider.*
4. **AWS Bedrock model / API.** *Recommend: Bedrock **Converse** + JSON schema (same mapping as today’s Responses fallback). User picks region + model id in Settings. No default AWS credential chain (`~/.aws`, instance role, ambient `AWS_*`).* Need a first-class model default? *Leave blank; require the user to set it.*
5. **Why-call (Fail sentence) on non-OpenAI providers.** Today a Fail may follow up on OpenAI `/responses`. *Recommend: use the selected provider if it can write a short sentence; if not (typical Jev), skip why and keep the cell reasons. Never fail a check because why failed.*
6. **OpenAI key dual-use.** Today `OPENAI_API_KEY` is both a live-harness fallback and the judge key. *Keep that when the scoring provider is OpenAI. Other providers need their own key and must not silently reuse OpenAI.*

---

## 0. Locked product decisions

These are not open questions except where §Open questions says so. If a later change fights one of these, the lock wins.

1. **One pack on disk** + `skillgate check` exit **0 or 1** (or **2** with no live harness key). No Skill Gate account.
2. **Built-ins stay.** The five Pass-lock judge questions + Path are always in the resolved bank. Pack cases that already exist (pdf 8/8, including `no-trigger-unrelated`) stay. Users **add** extra cases and extra judge questions on top (per skill, optionally project-wide). Schema stays **1**. See §3.
3. **Cannot delete built-in judge questions** (recommendation, pending Vignesh). They can be marked `on_fail: warn`. Path is already warn. Extra questions can be edited or removed.
4. **Low-confidence rule stays** when the provider returns confidence: a blocking `choice`/`score` that would Pass, with confidence missing or `< 0.5`, **keeps Pass** and warns: *The judge wasn't very sure about this one.* Never fails the check. Never blocks Deploy. Never changes exit 0/1. Default `0.5`. **If the provider has no confidence channel, do not warn** (same as today’s Responses fallback — do not warn on every Pass). Predicate answers have no official `confidence`; do not invent one.
5. **Trigger expectation and expected output stay case fields**, not judge questions. `should_trigger`, `contains` / golden, `output_path` remain in `evals/cases.yaml` and the Checks editor.
6. **`on_fail: block` vs `on_fail: warn`.** Block fails the check → Deploy refuses. Warn never flips `passed`. Path default warn; five built-ins default block.
7. **No-trigger cases still keep det ownership** (`expect_skill is None`). Extra questions on those cases are evidence only unless `judge.score_no_trigger: true` (off by default).
8. **BYO scoring provider, explicit keys only.** OpenAI Decisions, Jev, AWS (Bedrock), or OpenAI-compatible / other. Configured in Settings and `skillgate keys set` + `skillgate judge provider …`. **Never** ambient `OPENAI_API_KEY` / `AWS_*` / `AWS_PROFILE` / `~/.aws` unless `--key-env`. Same 0.5 key lock.
9. **Canonical question shape is Decisions-style.** Providers adapt *to* that shape (types `predicate` | `choice` | `score`). OpenAI Decisions is the reference adapter. Map the **same** resolved list (built-ins + extras) onto each provider.
10. **Customer copy is plain words** except chosen provider names in Settings (“OpenAI”, “Jev”, “AWS”, “Other”). Chrome: “Got the job done?”, “Yes/no”, “Pick one”, “Score”, “Fail the check”, “Warn only”, “Test connection”. `--json` may keep ids.
11. **Hosted reuses this code.** OSS `JudgeProvider` + `judge_spec`. Private TypeSafe/Jev becomes the **Jev adapter** (user or hosted key), not a private fork of the bank. Do not copy `jev_qa.py`; do not name a public module `jev_qa.py` (deny-list stays).
12. **UI after #19.** Phase 2 may ship schema + CLI + providers with no React editor. Phase 3 rebases onto merged #19 (black-and-white) for Settings + Checks. One `web/` tree for local and hosted.
13. **Responses / structured JSON remains a fallback mapping**, not a second product path: used by AWS Bedrock and by OpenAI-compatible endpoints that have no `/decisions`, and for the Fail why-call when the provider can write prose.

---

## 1. What exists today (facts, not hunches)

### 1.1 Scoring stack

| Piece | Path | Fact |
| --- | --- | --- |
| Fixed bank | `judge_bank.py` | Five Pass-lock `choice` questions + Path. `DEFAULT_MIN_CONFIDENCE = 0.5`. |
| HTTP | `judge_openai.py` | **Only** OpenAI Decisions (`gpt-6-luna`) + optional Responses fallback. |
| Resolve | `judge.resolve_judge` | `SKILLGATE_JUDGE=auto\|openai\|skip`. OpenAI or gateway key → Decisions. No Jev/AWS adapter in OSS. |
| Keys | `keys.py` | Vault names: `CURSOR_API_KEY`, `CODEX_API_KEY`, `OPENAI_API_KEY`, `AI_GATEWAY_API_KEY`, `ANTHROPIC_API_KEY`. Ambient ignored unless `--key-env`. |
| Settings UI | `settings-page.tsx` | Those five keys. OpenAI hint: “Scores live checks with your OpenAI key.” No provider picker, no Test connection. |
| Engine | `engine._live_verdict` | Skip → det owns. Error → fail closed. No-trigger → det owns. |
| Pack SoR | `evals/cases.yaml` schema 1 | Cases + `should_trigger` / golden / contains. **No `judge` field.** |
| Fingerprint | `PACK_FINGERPRINT_FIELDS` | Does **not** include questions. |
| Deny-list | `test_oss_surface.py` | Forbids `skillgate_ai.jev_qa` on disk and as an import. |
| Seed pack | `skills/pdf/evals/cases.yaml` | 8 pinned cases, including `no-trigger-unrelated`. |

Built-in judge questions:

| Key | Ask | Pass | Default `on_fail` |
| --- | --- | --- | --- |
| `task_completion` | Got the job done? | Fully completed | block |
| `correctness` | Got it right? | Correct | block |
| `instruction_adherence` | Followed the rules? | Fully followed | block |
| `evidence_action_validity` | Used the right evidence/actions? | Fully supported **or** N/A | block |
| `result_quality` | Delivered a good result? | Clear and complete **or** Mostly good | block |
| `path_efficiency` | Path | not in Pass lock | warn |

### 1.2 Already user-configurable (keep)

Checks editor today (`check-list.tsx`): trigger checkbox, Expected / Output file / fixtures, optional budgets. Adding a check already appends a card; pinning writes another case. **Gap:** nothing stops deleting a seed case in the UI — Phase 3 should lock seed/built-in rows if Vignesh confirms §Open questions 1.

### 1.3 UI facts and PR #19

- Primary UI is React `web/`, packaged as `web_static`.
- Settings and Checks are the two surfaces for this work. Vanilla `local_ui/static/` does not get a second editor.
- **#19** restyles `web/` to black and white (Geist, chroma only for Pass/Fail). Head `e5a2432`, draft. Do not restyle against `main` while it is open.
- `frontend-design`: reuse Field / Button / Select; no new palette.

### 1.4 Decisions API (reference mapping)

Official [Decisions guide](https://developers.openai.com/api/docs/guides/decisions) (2026-10-11): `POST /v1/decisions`, model `gpt-6-luna` only; types `predicate` | `choice` | `score`; unique `name`; predicate → `probability` (no `confidence` in the official excerpt); choice/score → `confidence` + `probabilities[]`. Score is a weighted average of **level indices from 0** and can fall between levels.

OpenAPI / downstream (not on the guide page): max **200** questions/request; choice **1–255** options; score **2–10** levels.

**Product cap:** **20** questions per resolved check = **6 built-ins + up to 14 extras**. Validate before HTTP.

---

## 2. What becomes user-configurable

| Lever | Scope | Default |
| --- | --- | --- |
| Scoring **provider** | Settings / `skillgate judge provider` | `auto`: OpenAI Decisions if an OpenAI/gateway key is set; else skip (det only). Never auto-pick Jev/AWS. |
| Provider **key** + endpoint | Settings / `skillgate keys set` | unset |
| Extra **cases** (checks) | Pack `cases:` + project extras | seed/existing cases stay |
| Extra **judge questions** | Pack / case / project `judge.extra_questions` | none; built-ins always included |
| Extra question type / ask / Pass bar / Fail vs warn | per extra question | — |
| Built-in question Fail vs warn | pack/project `judge.on_fail.<id>` | five block, Path warn |
| Low-confidence cutoff | pack/project `min_confidence` | `0.5`; behavior locked |
| Trigger / expected output | per case | unchanged |
| Score no-trigger with LLM | case `judge.score_no_trigger` | `false` |

Not in v1: deleting built-in questions (pending Vignesh); inventing confidence; averaging questions; free-form prose questions; ambient AWS/OpenAI keys; swapping Decisions off `gpt-6-luna` for the OpenAI adapter.

---

## 3. Where config lives

### 3.1 Questions — append, do not replace

**Supersedes** the earlier “replace the whole bank” draft.

Precedence for **extra** questions (all layers **append**, built-ins first):

1. Built-in six from `judge_bank.py` (always).
2. Project `skillgate.yaml` → `judge.extra_questions` (optional, committed; **not** `.skillgate/`).
3. Pack `evals/cases.yaml` top-level `judge.extra_questions`.
4. Per-case `cases[].judge.extra_questions`.

Ids must be unique across the resolved list. Extra id colliding with a built-in → error: “`{id}` is a Skill Gate question. Add a new id, or change Fail vs warn for the built-in.”

Optional `judge.on_fail:` map overrides severity for **built-in ids only** (`block` | `warn`). Cannot omit a built-in.

```yaml
schema: 1
skill: pdf
judge:
  min_confidence: 0.5
  on_fail:
    result_quality: warn          # still asked; no longer blocks Deploy
  extra_questions:
    - id: numbers_match
      type: predicate
      ask: Do the invoice totals in the output match the input PDF?
      on_fail: block
      pass_if: { gte: 0.8 }
cases:
  - id: extract-hello
    # … existing pdf case unchanged …
  - id: extract-invoice
    judge:
      extra_questions:
        - id: currency_usd
          type: choice
          ask: Is the extracted currency USD?
          on_fail: block
          choices:
            - { value: "Yes", description: "Amounts are in USD.", pass: true }
            - { value: "No", description: "A different currency.", pass: false }
  - id: my-new-check          # user-added case; the original 8 stay
    prompt: …
    should_trigger: true
```

Dump omits empty `judge:` so seed `cases.yaml` stays byte-stable until the user adds extras.

Project `skillgate.yaml` (committed extras, no secrets):

```yaml
judge:
  extra_questions: []
```

Provider choice and secrets do **not** live here.

### 3.2 Extra cases (checks)

- **Seed / existing pack cases stay.** Phase 3 UI: built-in/seed rows have no Remove (if Vignesh confirms).
- **Add check** appends a new case id (today’s dialog). Pin still writes `evals/cases.yaml`.
- **Project-wide extra cases** (optional): `skillgate.yaml` → `extra_cases:` copied into every pack at resolve time with ids prefixed `project-` to avoid collisions. *If this feels heavy, v1 can ship project-wide **questions** only and leave extra **cases** per-skill.* Flag: see §Open questions — treat project-wide **cases** as v1 if easy, else questions-only.

### 3.3 Per-extra-question fields

Same as Decisions mapping: `id`, `type` (`predicate` | `choice` | `score`), `ask`, `on_fail`, `choices` / `levels`, `pass_if`, optional `include_when: path_recorded`.

Built-in ids are reserved. Extra `id`: `^[a-z][a-z0-9_]*$`, ≤ 64 chars, not in `CHECK_CELL_ORDER` ∪ `SOFT_CELL_ORDER`.

### 3.4 Provider config (secrets vs settings)

| What | Where | Git |
| --- | --- | --- |
| Keys | `{project}/.skillgate/keys` (0600), or `SKILLGATE_*`, or `--key-env` | gitignored |
| Provider id, base URL, region, model | `{project}/.skillgate/judge` (0600 JSON) written by Settings / `skillgate judge provider set` | gitignored |
| Extra questions / cases | `evals/cases.yaml`, `skillgate.yaml` | committed |

New vault names (extend `PROVIDER_KEY_NAMES`; unknown name still errors plainly):

| Provider | Key name(s) | Non-secret in `.skillgate/judge` |
| --- | --- | --- |
| OpenAI Decisions | `OPENAI_API_KEY` (existing) | `provider: openai` |
| Jev | `JEV_API_KEY` (or reuse `AI_GATEWAY_API_KEY` if Vignesh prefers one gateway key — default: **dedicated `JEV_API_KEY`**) | `provider: jev`, optional `base_url` |
| AWS Bedrock | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` (optional `AWS_SESSION_TOKEN`) | `provider: aws`, `region`, `model` |
| Other / OpenAI-compatible | `AI_GATEWAY_API_KEY` (existing) or a dedicated compatible key | `provider: compatible`, `base_url`, optional `decisions_path` default `/decisions` |

CI: `SKILLGATE_JEV_API_KEY`, `SKILLGATE_AWS_ACCESS_KEY_ID`, `SKILLGATE_AWS_SECRET_ACCESS_KEY` overlays. **No** ambient `AWS_ACCESS_KEY_ID`.

`.skillgate/judge` example (no secrets):

```json
{
  "provider": "openai",
  "region": null,
  "model": null,
  "base_url": null
}
```

Fingerprint **pack** questions (extras + on_fail overrides), not the local provider — so switching a laptop from OpenAI → AWS does not by itself invalidate Deploy trust. Changing extras does.

---

## 4. Judge-provider interface

### 4.1 Protocol (OSS, shared with hosted)

Canonical input = resolved `JudgeSpec` (built-ins + extras) + the same JSON **state** Decisions uses today (prompt, expect/selected skill, scorer rows, artifacts, golden/actual, path, transcript tail, optional images).

```
JudgeProvider
  id: openai | jev | aws | compatible
  display_name: str
  supports_confidence: bool
  supports_probabilities: bool
  evaluate(*, state, spec, images, timeout) -> {status, answers, usage?, reason?}
  ping() -> {ok: bool, message: str}   # Test connection; never log the key
```

`answers` is **normalized** to the Decisions-shaped dict used by `verdict()`:

- `choice`: `{choice, confidence?, probabilities?}`
- `predicate`: `{probability}`
- `score`: `{score, confidence?, probabilities?}`

Missing required field → unusable (fail closed for `on_fail: block`; warn for warn-only). Adapters **must not invent** `confidence` or `probabilities`.

`OutcomeJudge` (rename conceptually to “applies spec + Pass lock”; keep module split) calls `provider.evaluate` then `verdict(spec, answers)` then low-confidence warnings **only if** `supports_confidence` and a blocking choice/score returned a numeric confidence.

`SkipJudge` remains when pref is skip or no provider key.

### 4.2 Adapters

| Adapter | Transport | How questions map | Confidence | `<0.5` warning |
| --- | --- | --- | --- | --- |
| **OpenAI Decisions** (reference) | `POST {openai}/v1/decisions`, `gpt-6-luna` | spec → `questions[]` as today | choice/score: yes. predicate: no | Yes, on blocking choice/score Pass with missing/`< min` confidence |
| **Jev** | User `JEV_API_KEY` + configured base URL. Do **not** vendor `jev_qa.py`. New module e.g. `judge_providers/jev.py`. | Built-in six → existing Jev/TypeSafe cells. Extras: send if the API accepts extra named questions; otherwise §Open questions 2 | **Hunch:** may return scores; persist if present, never invent | Apply only when a numeric `confidence` is actually present on a blocking choice/score |
| **AWS Bedrock** | Bedrock **Converse** (region + model from Settings). IAM key from vault only | spec → JSON schema (same shape as `structured_output_schema()`), one tool/JSON response | **No** native Decisions confidence | **Do not warn** (no channel) |
| **OpenAI-compatible / other** | `base_url` + key. Try `POST {base}/decisions` first if `decisions_path` set/default; if 404, structured JSON on `/chat/completions` or `/responses` | Same spec | If the `/decisions` body includes `confidence`, treat like OpenAI. Structured-JSON fallback: no | Warn only when confidence is present |

OpenAI-compatible **with** a working `/decisions` is how “any compatible provider” stays honest. A random chat model gets the structured-JSON mapping (choice enums / score levels / predicate 0–1), not fake probabilities.

Images: JPEG/PNG data URLs only on adapters that document vision (OpenAI Decisions, compatible `/decisions`). Bedrock: include images only if the chosen model’s Converse vision is documented; otherwise omit and score from text (same fail-closed as omitted images today). Jev: follow whatever that endpoint already accepts; do not invent `file_id`.

### 4.3 Resolve order

```
skillgate judge provider set   →  .skillgate/judge.provider
SKILLGATE_JUDGE=skip           →  SkipJudge (unchanged)
SKILLGATE_JUDGE=openai         →  force OpenAI adapter (need OpenAI key)
auto + provider file           →  that adapter
auto + no provider file        →  today’s auto (OpenAI/gateway key → Decisions, else skip)
```

Explicit provider without its key → exit **2**: “Add a {OpenAI / Jev / AWS} key in Settings (`skillgate keys set`), or pick a different scoring provider.”

### 4.4 Test connection

CLI: `skillgate judge provider test`. Settings: **Test connection**.

Behavior: `ping()` — smallest legal request (Decisions: one `predicate` “Is this a connection test?” on input `"ping"`; Bedrock: Converse with max 1 token / tiny schema; Jev: documented health or a one-cell evaluate). Success: “Connected to {display_name}.” Failures: existing friendly HTTP map (401 key, 403 not enabled, 404 no endpoint, 429 quota, timeout) with the **provider’s** plain name, never a traceback, never the key.

Do not run `ping()` in merge CI. Unit-test with mocked HTTP.

### 4.5 Why-call

Keep “one short Fail sentence, ignore errors.” Provider-specific: OpenAI/compatible → `/responses` or chat JSON `{why}`; AWS → Converse JSON `{why}`; Jev → skip if no prose channel. Pending Vignesh §Open questions 5.

---

## 5. CLI

```
skillgate keys set OPENAI_API_KEY | JEV_API_KEY | AWS_ACCESS_KEY_ID | …
skillgate judge show [PACK] [--case ID]
skillgate judge reset [PACK]          # drop extras + on_fail overrides; built-ins remain
skillgate judge provider show
skillgate judge provider set openai|jev|aws|compatible [--base-url] [--region] [--model]
skillgate judge provider test
```

| Command | Behavior |
| --- | --- |
| `judge show` | Print built-ins (locked) then extras, in plain words. `--json` dumps resolved spec (no secrets). |
| `judge reset` | Remove pack `judge.extra_questions` / `on_fail`. Built-ins stay. |
| `judge provider show` | “Scoring with OpenAI (your key)” / “No scoring provider — file checks only.” |
| `judge provider set` | Writes `.skillgate/judge`. Does not print keys. |
| `judge provider test` | `ping()`; exit 0/1; plain message. |

`skillgate check` uses the resolved spec + selected provider. No `--questions` flag.

`keys set` hint lists the new names. Ambient still ignored.

---

## 6. Validation and friendly errors

Reuse `SuiteError` + `friendly_validation_error`. Author mistakes exit **2**; scored Fail exit **1**; missing provider key exit **2**.

| Mistake | Message |
| --- | --- |
| Extra id `task_completion` | `` `task_completion` is a Skill Gate question. Add a new id, or change Fail vs warn for the built-in. `` |
| Extra type `ranking` | `Question {id}: type must be yes/no, pick one, or score.` |
| 15 extras (21 total) | `A check can ask at most 20 scoring questions (Skill Gate’s 6 plus yours).` |
| AWS provider, no region | `AWS scoring needs a region in Settings.` |
| AWS provider, no key | `Add an AWS key in Settings (`skillgate keys set AWS_ACCESS_KEY_ID`).` |
| Ambient-only `AWS_ACCESS_KEY_ID` | ignored; same as OpenAI ambient |
| Compatible 404 on `/decisions` then JSON fallback fails | `This endpoint did not accept scoring requests. Check the base URL.` |
| Jev extras unsupported (if that is the lock) | `Jev scores Skill Gate’s built-in questions only. Extra questions need OpenAI or another provider.` |

---

## 7. Backward compatibility

| Surface | After Phase 2 |
| --- | --- |
| `skills/pdf` (no `judge:`) | Same 8 cases, same six questions, same Pass lock |
| `skills/pdf-sabotaged` | Unchanged red twin |
| User schema-1 packs | Load as today; extras optional |
| No scoring key | `SkipJudge`; det scorers; exit 0/1/2 unchanged |
| `SKILLGATE_JUDGE` / `SKILLGATE_JUDGE_BACKEND=responses` | Still work for the OpenAI adapter |
| Docker `CMD check /pack` | Unchanged; keyless exit 2 |
| History JSONL | Additive `provider` / extra cells |
| Hosted Jev | Same wheel protocol; private wrapper implements or **is replaced by** OSS `judge_providers/jev.py` |

Do **not** rewrite seed `cases.yaml`. `judge reset` deletes extras only.

---

## 8. UI (Phase 3 — after PR #19)

One `web/` tree. Black-and-white tokens from #19. No new route.

### 8.1 Settings (provider + key + test)

Below today’s key rows:

- **Scoring provider** — Select: OpenAI · Jev · AWS · Other (OpenAI-compatible). Default Auto (hidden as “Auto (OpenAI when a key is set)”).
- Conditional fields: AWS region + model; Other base URL; Jev optional base URL.
- Matching key row(s) with the same hide/show pattern as today.
- **Test connection** — calls `POST /api/judge/ping`. Toast: “Connected to OpenAI.” / the plain error.
- Copy: “This key scores live checks. It is not read from your shell unless you pass `--key-env`.”

Do not show “Decisions”, “Bedrock Converse”, “gpt-6-luna” in chrome. Model/region are Settings fields, so those ids may appear as the user’s values.

### 8.2 Checks editor

Skill page → Checks tab.

- Existing cards for the pack’s cases. Seed/built-in cases: **no Remove** (pending Vignesh). **Add check** appends.
- Per card, accordion **Scoring questions**:
  - Built-in six as locked rows (ask text read-only). Control: **Fail the check** / **Warn only**.
  - Extra questions: full editor (type, ask, options, Pass bar, Fail vs warn, Remove).
  - **Add scoring question**. Disable at 20 total.
  - Hint: “Skill Gate always asks the first six. Yours run in the same scoring request.”
- Pack-level extras accordion above the list (skill-wide `extra_questions` + `on_fail`).
- Trigger / Expected / Output / budgets unchanged.

Result panel: built-in chips first, then extra chips. Checking motion unchanged (700 / 350 / 400).

### 8.3 API

- `GET/PUT /api/settings/judge` — provider file, no secrets in GET (presence flags only).
- `POST /api/judge/ping` — test connection.
- Pin path already writes cases; extend `Check` with `judge.extra_questions` / `on_fail`.
- `checks_from_pack` round-trips extras.

---

## 9. Hosted app (one codebase)

1. Pin the wheel that contains `judge_spec` + `JudgeProvider`.
2. Hosted Jev: implement or wrap as `judge_providers/jev.py` using the hosted endpoint/key policy. **Same spec, same verdict.**
3. Settings + Checks are the OSS React app (`status.mode === "cloud"` can keep billing slots hidden; scoring provider stays visible).
4. Do not keep a private copy of ordinals.
5. This Phase 1 PR does **not** touch the private repo.

---

## 10. Files (Phase 2 vs Phase 3)

### Phase 2 — create

| Path | Why |
| --- | --- |
| `src/skillgate_ai/judge_spec.py` | Built-ins + extras merge, validate, Decisions payload, verdict |
| `src/skillgate_ai/judge_providers/` | Protocol + `openai.py`, `jev.py`, `aws.py`, `compatible.py`, `ping` |
| `tests/test_judge_spec.py` | Append extras, reserved ids, on_fail override, caps |
| `tests/test_judge_providers.py` | Mocked HTTP per adapter; no invented confidence; ping |
| `tests/test_judge_cli.py` | `show` / `reset` / `provider set|show|test` |

### Phase 2 — change

| Path | Why |
| --- | --- |
| `judge_bank.py` | Stay the built-in constants; verdict delegates to spec |
| `judge_openai.py` | Become the OpenAI adapter (keep module or thin-wrap) |
| `judge.py` / `engine.py` / `gate.py` | Resolve provider + spec |
| `keys.py` / `config.py` | New vault names; load `.skillgate/judge`; never ambient AWS |
| `case_pack.py` | `judge.extra_questions`, `on_fail`; fingerprint extras |
| `cli.py` | `judge` group |
| `errors.py` | loc labels + provider messages |
| `report.py` | Extra cells; provider display name |
| `docs/pack.md`, `docs/openai-judge.md`, `README.md` | Providers + extras-on-top |
| existing judge/keys tests | Auto path unchanged; new names in `keys set` hint |

### Phase 2 — do not change

Docker `ENTRYPOINT`/`CMD`, seed `cases.yaml` **contents**, Checking motion, `web/` (wait for #19), deny-list `jev_qa`, private repo, PyPI version (**0.6.0** on the implementation PR, not this one).

### Phase 3 — after #19

`settings-page.tsx`, `check-list.tsx`, `add-check-dialog.tsx`, `eval-page.tsx`, `types.ts`, `api.ts`, vitest, rebuild `web_static`.

---

## 11. Test plan (TDD)

Write failing tests first; never weaken.

**Built-ins + extras**

1. Pack without `judge:` → six questions identical to today.
2. Pack extras append **after** built-ins; HTTP `questions[].name` is six + extras.
3. Extra id `correctness` → SuiteError, no HTTP.
4. `on_fail.result_quality: warn` → quality miss does not fail; other built-ins still can.
5. Per-case extras append for that case only.
6. Project `skillgate.yaml` extras apply to every pack; pack extras follow.
7. Adding a ninth pdf case does not drop the original eight.
8. `judge reset` drops extras, keeps six.
9. Dump: no `judge:` key on seed packs.

**Providers**

10. OpenAI adapter: `/v1/decisions`, six+extras, confidence warning path unchanged.
11. Compatible adapter: `/decisions` 200 with confidence → warn rule; `/decisions` 404 then JSON schema → **no** confidence warning on Pass.
12. AWS adapter: Converse mocked; no `AWS_*` from ambient; missing region exit 2.
13. Jev adapter: mocked evaluate; no import of `jev_qa`; extras per Vignesh lock.
14. `provider test` 401 → “did not accept this API key”; secret absent from logs.
15. Explicit `aws` without key → exit 2, Settings hint.
16. `auto` with only Cursor key → SkipJudge (today).

**Existing**

17. Low-confidence Pass; no-trigger det-owns; pdf/sabotaged contracts; `test_oss_surface.py`; `test_keys.py` ambient ignore includes `AWS_ACCESS_KEY_ID`.
18. Full CI locally before push: pytest, pnpm test, gate keyless exit 2, web-build, oss-surface, docker.

Phase 3: vitest for locked built-in rows, Add question, Test connection, provider select. Browser: Settings ping + Checks add-on, desktop and narrow viewport, after #19 tokens.

---

## 12. Risks

| Item | Status | Mitigation |
| --- | --- | --- |
| PR #19 vs Settings/Checks | Fact | Phase 3 after merge |
| Jev extras | Unknown API | §Open questions 2; adapter must not pretend |
| Bedrock JSON ≠ Decisions calibration | Fact | Do not claim parity; same ordinals only |
| Invented confidence | Tempting on Bedrock | Forbidden; skip warning |
| AWS credential chain | Easy footgun | Vault only; tests prove ambient ignore |
| `jev` deny-list / jargon tests | Fact | New module name; Settings copy exception once it is a provider |
| Dual OpenAI key meaning | Fact | Document; other providers never reuse it |
| Fingerprint vs provider switch | Choice | Questions yes, provider no |
| 20-cap vs 14 extras | Product | Friendly error before HTTP |

---

## 13. Implementation order

1. **This PR (Phase 1):** this document. Draft PR. Stop.
2. **Phase 2a:** `judge_spec` extras-on-top + reserved ids + tests (still OpenAI-only HTTP).
3. **Phase 2b:** provider protocol + OpenAI adapter extracted; `auto` behavior unchanged.
4. **Phase 2c:** compatible + AWS + Jev adapters, ping, keys, `judge provider` CLI; ambient-AWS tests.
5. **Phase 2d:** pack schema dump/fingerprint; `judge show/reset`; docs.
6. **Phase 2e:** full CI; Thermos; implementation PR; version **0.6.0**.
7. **Phase 3:** after #19; Settings + Checks; `web_static`; browser verify.
8. **Hosted:** pin wheel; Jev adapter.

---

## 14. Out of scope (this PR and v1)

- Implementing any of the above in this branch
- Merging or rebasing onto PR #19
- Rewriting seed pdf cases
- Ambient OpenAI/AWS keys or default AWS credential chain
- Making low-confidence a Fail
- Deleting built-in questions (unless Vignesh overrides §Open questions 1)
- Marketplace / hosted billing
- Vanilla `local_ui` Settings/Checks editor
- Private `skillgate-ai` repo edits in this PR

---

## 15. This PR

Plan only: `docs/plans/custom-judge-checks.md`. Incorporates the 2026-10-11 scope change (BYO provider + extras on top of built-ins). Base `main` (0.5.0). Draft. No code, no version bump, no UI restyle.
