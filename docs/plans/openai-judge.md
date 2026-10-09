# OpenAI judge provider — Implementation Plan

> **Phase 2 implements this plan** on OSS `vigneshm1995personal/skillgate`. Do **not** copy private `jev_qa.py`. Do **not** bump/publish the PyPI version in this PR. Do **not** flip this repo public.

**Goal:** Let a user score live checks with **their own OpenAI API key**. **v1 scores with the Decisions API** (`POST /v1/decisions`, `gpt-6-luna` only) as the primary backend — that is the product-owner lock after the official guide confirmed public beta for standard keys. Same fixed questions the hosted TypeSafe judge answers today, same Pass/Fail lock, same report shape. The rest of the gate (`skillgate check` exit 0/1, history JSONL, Docker `ENTRYPOINT`/`CMD`, copy-paste GitHub Action) stays unchanged.

**Parent (locked):** [`docs/plans/2026-10-03-skillgate-oss-extract.md`](2026-10-03-skillgate-oss-extract.md). Decision rule unchanged: if a feature cannot work as **one pack on disk** plus `skillgate check` exiting **0 or 1** with **no Skill Gate account**, it does not belong here. OpenAI judge = the user’s key only. The built-in checker stays the skip/fallback when no OpenAI key is set.

Inspected OSS tree: `main` @ `6a3b0d3` (`Hold Checking then draw Passed or Failed on Run live (#7)`). PyPI dist **`skillgate-ai` 0.3.0**. CLI command **`skillgate`**. Hosted app stays private at [`vigneshm1995personal/skillgate-ai`](https://github.com/vigneshm1995personal/skillgate-ai).

Private judge source of truth (read-only, **do not copy the file**): `src/skillgate_ai/jev_qa.py` on private `skillgate-ai` (`run_jev_outcome_judge`, `CHECK_CELL_ORDER`, `_PASS_LOCK`, `SOFT_CELL_ORDER`). Hosted engine still hard-calls Jev (`run_jev_outcome_judge` inside private `engine._run_outcome_judge`); OSS already stripped that import.

Official OpenAI citations in this doc were re-fetched **2026-10-07**. Shapes below are only from those pages.

---

## 0. What exists today (facts, not hunches)

### 0.1 OSS call chain

| Piece | Path | What it does |
| --- | --- | --- |
| `Judge` protocol | `src/skillgate_ai/judge.py` | `(goal, artifacts, transcript_tail, **kwargs) -> {passed, cells, ...}`. Skip sets `status=skip`, `passed=None`. |
| Default | `judge.default_judge()` → `SkipJudge` | Det scorers own red/green. |
| Call site | `engine._run_outcome_judge` | Live harnesses only (`harness.is_live_harness`: `cursor-agent` / `codex` / `llm`). Builds artifact rows + golden/actual, then `judge.judge(...)`. Demo never calls a live judge. |
| Verdict | `engine._live_verdict` | If `status==skip` or `passed is None` → keep det AND. If `passed` is a bool → **override** det. Binary/missing-output mismatch still fails closed. |
| Gate | `gate.run_check` | Resolves pack, harness, `run_eval`, history, exit 0/1/2. **Does not pass `judge=`** today, so every OSS run uses `SkipJudge`. |
| CLI | `cli._run_gate` → `gate.run_check` | Exit code is the product. |
| History | `history.append_eval` | Pack-local JSONL of `report_to_dict` (already includes `tasks[].judge`). |
| Report | `report.report_to_dict` / `format_cli` / `format_github` | Judge blob rides on each task. CLI/GitHub summaries do **not** currently name which judge scored. |
| Live HTTP | `harness._gateway_complete_response` | User `OPENAI_API_KEY` / `AI_GATEWAY_API_KEY` → `POST {base}/chat/completions` for the **harness**, not the judge. `httpx` is already a required dep. |
| Keys | `config.ROOT_ENV_NAMES` | Already includes `OPENAI_API_KEY`. Wizard + pack-page details write it via `PUT /api/env`. |
| UI motion | `local_ui/static/app.js` | Checking hold (`CHECKING_MIN_MS = 700`) → slide → drawn Passed/Failed. Tests in `tests/test_local_ui.py` lock this. |
| Deny-list | `tests/test_oss_surface.py` | Forbids `skillgate_ai.jev_qa` on disk and as an import. |
| Image sniff | `case_pack.sniff_output_bytes` | JPEG / PNG / GIF / PDF magics. No vision upload today — judge state is JSON metadata (path, present, kind, size). |

### 0.2 Hosted TypeSafe questions (private `jev_qa.py`, not in this tree)

One bounded request per **live** task. Never free-form questions invented per run.

**Pass lock (all required; no averages).** Comparison is case-insensitive after `.strip().lower()`:

| Internal key | User-facing label | Allowed ordinals for Pass |
| --- | --- | --- |
| `task_completion` | Got the job done? | `Fully completed` |
| `correctness` | Got it right? | `Correct` |
| `instruction_adherence` | Followed the rules? | `Fully followed` |
| `evidence_action_validity` | Used the right evidence/actions? | `Fully supported` **or** `N/A` |
| `result_quality` | Delivered a good result? | **Soft:** `Clear and complete` **or** `Mostly good` (Pass); `Significant issues` / `Poor` → Fail |

Full choice lists (must be the Decisions `choices[].value` strings):

- `task_completion`: Fully completed / Partially completed / Not completed
- `correctness`: Correct / Mostly correct / Incorrect / Insufficient evidence
- `instruction_adherence`: Fully followed / Minor deviation / Major deviation / Violated
- `evidence_action_validity`: Fully supported / Partially supported / Unsupported / N/A
- `result_quality`: Clear and complete / Mostly good / Significant issues / Poor

**Soft cell (same request, not in the Pass lock):**

| Internal key | User-facing label | Ordinals |
| --- | --- | --- |
| `path_efficiency` | Path | Efficient / Acceptable / Looping / Wasteful |

`path.steps` is supporting context only. Metrics budgets (`metrics.py`) remain a **Gate block**, not a judge Fail — do not fold path-efficiency into `passed`.

Hosted extra (OSS `_live_verdict` does **not** do this today): no-trigger cases (`expect_skill is None`) keep **det** ownership; the five-cell bank is evidence only. Phase 2 should match that when a live judge is active, so an unrelated-prompt skip cannot fail on “Not completed”.

Hosted skip-without-key **fails closed**. OSS must **not** copy that: no OpenAI key → `SkipJudge` → built-in checker (roadmap rule).

### 0.3 Keys vs judge vs harness (easy to mix up)

`OPENAI_API_KEY` already means two things in OSS:

1. Live **harness** fallback (`config.py`: `codex_api_key = CODEX_API_KEY or OPENAI_API_KEY`; also BYO `llm` chat).
2. After this work: live **judge** key.

A Cursor-only user can run live without OpenAI. A user with only `OPENAI_API_KEY` both runs and scores with that key. That is intended.

---

## 1. Locked product constraints

1. One pack on disk + `skillgate check` exit **0 or 1**, no Skill Gate account.
2. OpenAI judge uses the **user’s** `OPENAI_API_KEY` only. Never a Skill Gate-owned key. Never log or print the key (headers, traces, history, UI, CLI).
3. No key / `SKILLGATE_JUDGE=skip` / demo harness → built-in checker. Det fixtures stay unlimited.
4. Same questions, same Pass lock, same `tasks[].judge` shape as hosted TypeSafe, so history / `check` / Docker / Action stay compatible. Extra fields (`confidence`, `probabilities`, `why`) are additive.
5. Customer copy is plain. Do **not** show “Jev”, “Jev cells”, “harness”, “BYOLLM”, “Option A” unless already user-facing (OSS UI already forbids `jev` in `test_ui_copy_has_no_internal_jargon`).
6. Reuse Checking → slide → drawn Passed/Failed. No new hold screen, no “Evaluating”.
7. Errors (bad key, quota, model missing, Decisions 403/404/400, timeout) → clear message, **fail the check**, never silent Pass, never a traceback as the primary UX.
8. Do not add `openai` as a required PyPI dep. Use existing `httpx`.
9. Do not import or vendor `jev_qa.py`. Re-home the **cell bank + Pass lock** in OSS (`skillgate_ai.judge_bank`); private TypeSafe imports that bank from the wheel.
10. Implementation PR bumps package version **0.3.0 → 0.4.0** (this plan PR does not).
11. **v1 default backend is Decisions.** Responses + Structured Outputs is a selectable fallback (`SKILLGATE_JUDGE_BACKEND=responses`) and the Fail “why” writer. Do not silently switch backends on 403.

---

## 2. OpenAI: verified from official docs (2026-10-07)

### 2.1 Model id — verified

**Default (and Decisions-only) model: `gpt-6-luna`.**

Citations: [GPT-6 Luna](https://developers.openai.com/api/docs/models/gpt-6-luna), [Models catalog](https://developers.openai.com/api/docs/models), [Decisions guide](https://developers.openai.com/api/docs/guides/decisions) (“Currently, only `gpt-6-luna` is supported”).

Config override `SKILLGATE_JUDGE_MODEL` still exists for the **Responses fallback / why-call**. Decisions requests must send `gpt-6-luna` unless OpenAI later documents another Decisions model — do not send Astra/Sol to `/v1/decisions`.

Luna on ordinary Responses/Chat Completions (why-call and fallback backend): Structured outputs **Supported**; input **$0.10 / 1M**, output **$0.50 / 1M** ([model page](https://developers.openai.com/api/docs/models/gpt-6-luna)). `reasoning.effort` supports `none`, `low`, `medium` (default), `high`, `xhigh`, `max`.

### 2.2 Decisions API — v1 primary backend (verified)

Citation: [Decisions](https://developers.openai.com/api/docs/guides/decisions) (markdown: [decisions.md](https://developers.openai.com/api/docs/guides/decisions.md)).

Facts from that page:

- Public beta; GA “in the coming weeks”.
- `POST https://api.openai.com/v1/decisions`
- Only model: `gpt-6-luna`
- Request parts: `model`, `input` (text string **or** user messages with text and images), `questions[]`
- Question types: `predicate` | `choice` | `score`
- Response: `answers[]`, each echoing `name`
- `choice` answer: `choice`, `probabilities[]` (`value` + `probability`), `confidence`
- `score` answer: `score` (probability-weighted average of **level indices starting at 0**), `probabilities[]` (`value` index, `label`, `probability`), `confidence`
- `predicate` answer: `probability` (0–1 that the condition is true). **No `confidence` field in the official predicate excerpt.**
- Multiple independent questions in one `questions` array share `input`
- Decisions returns **typed answers, not prose**. The same page says to use [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) with the Responses API when you need a written explanation
- Images: **inline base64 data URLs only**. Hosted HTTP/HTTPS URLs and `file_id` are **not** supported
- Pricing on `/v1/decisions`: **$0.10 per 1M input tokens**; no cache-read, cache-write, or output-token charges. Regional premiums and long-context input multipliers apply. Other Luna endpoints use the model/pricing page instead

**Interpret the answers** (same page): set thresholds from labeled examples based on the cost of false positives vs false negatives. OpenAI does **not** publish a numeric confidence cutoff.

**Not on that page (do not invent):** Python SDK method, per-question rate limits, a published byte/patch cap for Decisions images, a `refusal` question type, output-token charges.

### 2.3 Structured Outputs — fallback backend + Fail “why” (verified)

Citation: [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

- `POST https://api.openai.com/v1/responses`
- `text.format`: `{type: "json_schema", name, schema, strict: true}`
- Enums are a documented schema feature; every property `required`; `additionalProperties: false`
- Refusals: `output[].content[]` with `type: "refusal"` (not schema JSON)

This is **not** how v1 scores the six questions by default. It is (a) `SKILLGATE_JUDGE_BACKEND=responses` if Decisions is unusable for a given key, and (b) the one optional why-call after a Fail.

---

## 3. Map Skill Gate questions → Decisions types

Official type rule ([Decisions](https://developers.openai.com/api/docs/guides/decisions)): use **`choice` for categories without an order**; use **`score` for ordered levels** (severity). `score` “can fall between levels”; “Use `choice` to select a single category.” `predicate` is for a yes/no condition and returns only `probability`.

Our Pass lock needs **one named ordinal per question** (the chip + the lock). A between-level float cannot be the chip.

### 3.1 Five Pass-lock questions → `choice` (not `predicate`)

None of the five are binary. Collapsing them to a predicate (“is this a Pass?”) would hide ordinals the lock cares about (`Mostly good` vs `Clear and complete`, `N/A` vs `Fully supported`). A documented predicate threshold (the page says pick your own) would also be a **new** Pass rule, which is forbidden.

| `name` | `type` | `choices[].value` | `choices[].description` |
| --- | --- | --- | --- |
| `task_completion` | `choice` | Fully completed / Partially completed / Not completed | Existing TypeSafe criteria text |
| `correctness` | `choice` | Correct / Mostly correct / Incorrect / Insufficient evidence | same |
| `instruction_adherence` | `choice` | Fully followed / Minor deviation / Major deviation / Violated | same |
| `evidence_action_validity` | `choice` | Fully supported / Partially supported / Unsupported / N/A | same |
| `result_quality` | `choice` | Clear and complete / Mostly good / Significant issues / Poor | same |

`instructions` = the user-facing label plus “Pick exactly one.” Distinct descriptions come from the hosted criteria strings (port into `judge_bank`).

Pass rule **unchanged**: lowercase `choice` must sit in `_PASS_LOCK`. Map each Decisions answer to hosted shape `answers[name] = {"choice": <value>}`.

### 3.2 Soft Path → `choice`, not `score`

**Justification (official + product):**

1. [Decisions](https://developers.openai.com/api/docs/guides/decisions): “Use `choice` for categories without an order.” Efficient / Acceptable / **Looping** / **Wasteful** are not a single severity ladder. Looping (repeated same tools) and Wasteful (off-task thrashing) are different failure **modes**. Adjacent `score` levels must have distinct ordered criteria; inventing “Wasteful is worse than Looping” is a hunch, not the bank.
2. Same page: `score` is a **weighted average of indices** and **can fall between levels** (their example: `1.1`). The report chip and hosted `soft_answers.path_efficiency.choice` need **one** ordinal.
3. Same page: “The score summarizes the distribution across levels. Use `choice` to select a single category.”

So Path is a sixth `choice` on the **same** Decisions request (`name`: `path_efficiency`; values Efficient / Acceptable / Looping / Wasteful; descriptions from `_SOFT_OUTCOME_QUESTIONS`). Still **not** in the Pass lock.

If a later calibration pass wants a 0–3 efficiency rubric, that would be a new question, not this bank.

### 3.3 Canonical Decisions request (v1 score call)

`POST https://api.openai.com/v1/decisions`

Auth: `Authorization: Bearer $OPENAI_API_KEY`. Never log the bearer token.

```json
{
  "model": "gpt-6-luna",
  "input": [
    {
      "role": "user",
      "content": [
        {"type": "input_text", "text": "<JSON state: check prompt, expect/selected skill, scorer rows, artifact metadata, golden/actual text, path.steps, transcript tail>"},
        {"type": "input_image", "image_url": "data:image/png;base64,<...>"}
      ]
    }
  ],
  "questions": [
    {
      "type": "choice",
      "name": "task_completion",
      "instructions": "Got the job done? Pick exactly one.",
      "choices": [
        {"value": "Fully completed", "description": "The requested work is fully done."},
        {"value": "Partially completed", "description": "Some of the requested work is done but incomplete."},
        {"value": "Not completed", "description": "The requested work was not done."}
      ]
    }
  ]
}
```

(Five more `choice` questions in the same array: the remaining Pass-lock keys + `path_efficiency`.) When there are no images, `input` may be a **string** (official complaint-routing example).

Illustrative `choice` response (official excerpt, department example):

```json
{
  "answers": [
    {
      "type": "choice",
      "name": "department",
      "choice": "billing",
      "probabilities": [
        {"value": "billing", "probability": 0.95},
        {"value": "technical", "probability": 0.02}
      ],
      "confidence": 0.93
    }
  ]
}
```

Stamp every Skill Gate cell the same way. If `answers` is missing a required `name`, or `choice` is not in the supplied values → `status=error`, fail closed (never Pass).

---

## 4. Confidence / probabilities (soft) and low-confidence behavior

### 4.1 Record (additive, not a new Deploy block)

On each Pass-lock and Path cell, persist under `tasks[].judge` (history already stores the judge dict):

```python
answers[name] = {
  "choice": str,                 # hosted field; Pass lock reads this
  "confidence": float | None,    # Decisions choice field
  "probabilities": [             # Decisions array, copied not invented
    {"value": str, "probability": float},
    ...
  ],
}
```

`cells[name]` stays `{label, choice, reason}` for UI chips. Put `confidence` on the cell too so the UI can show it later without digging. Path lives in `soft_answers` with the same extra fields.

`metrics.py` budgets and `blocks_deploy` **do not** change because of confidence. Low confidence is **not** a Gate fail and does **not** change `skillgate check` exit 0/1.

### 4.2 Low-confidence: keep Pass, warn (owner lock)

OpenAI: pick a threshold from labeled examples ([Interpret the answers](https://developers.openai.com/api/docs/guides/decisions#interpret-the-answers)). This repo has none yet.

**Default (product choice, not an OpenAI number):** `SKILLGATE_JUDGE_MIN_CONFIDENCE=0.5`.

Apply only to **Pass-lock** `choice` answers (`CHECK_CELL_ORDER`) on the **Decisions** backend (the one that returns `confidence`). Never Path. Never the Responses fallback (no confidence channel — do not warn on every Pass).

1. If `choice` is missing or not a supplied enum value → **Fail closed** (“OpenAI scoring returned an unusable answer.”). Exit 1. This is not a confidence case.
2. If `choice` is outside `_PASS_LOCK` → Fail (unchanged). Record confidence.
3. If `choice` is inside `_PASS_LOCK` and `confidence` is missing, non-numeric, or `< min` → **keep Pass**. Record confidence/probabilities. Add a plain warning: *The judge wasn't very sure about this one.* Do **not** change `passed` or the process exit code.
4. If all five Pass-lock cells are in-lock and each `confidence >= min` → Pass with no warning (JPEG/missing-output mismatch can still fail).

Do **not** also threshold `probabilities[].probability` in v1.

---

## 5. Fail “why” — one optional Responses follow-up

Decisions does not return explanation text ([Decisions](https://developers.openai.com/api/docs/guides/decisions) points you to Structured Outputs for that).

**When:** after the Decisions (or fallback) verdict is computed, if the check **Failed** (Pass lock miss, unusable choice, or output mismatch). Skip on a clean Pass, including a Pass that only has a low-confidence warning.

**What:** exactly **one** `POST /v1/responses` with `gpt-6-luna`, Structured Outputs, short plain-words `why` for the UI Fail line.

```json
{
  "model": "gpt-6-luna",
  "max_output_tokens": 128,
  "reasoning": {"effort": "low"},
  "input": [
    {
      "role": "system",
      "content": "Explain in one or two short sentences why this check failed. Use everyday words. Do not mention APIs, schemas, or internal field names."
    },
    {
      "role": "user",
      "content": "<check prompt + failing cell labels/choices + transcript tail; no secrets>"
    }
  ],
  "text": {
    "format": {
      "type": "json_schema",
      "name": "check_fail_why",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {"why": {"type": "string"}},
        "required": ["why"],
        "additionalProperties": false
      }
    }
  }
}
```

Citations: Responses Structured Outputs curl in [structured-outputs](https://developers.openai.com/api/docs/guides/structured-outputs); Luna `reasoning.effort` on the [model page](https://developers.openai.com/api/docs/models/gpt-6-luna). `max_output_tokens: 128` is a **product bound** (Responses supports the field). `reasoning.effort: "low"` is a supported Luna value, not a documented “judge mode”.

**Hard rule:** if this call 401s, 403s, 429s, times out, refuses, or returns empty `why`, **leave the verdict unchanged**. Set `judge.why` to omitted/null and keep Pass-lock reasons. Never fail a check *because* the why-call failed; never Pass a check because it succeeded.

Optional kill switch: `SKILLGATE_JUDGE_WHY=0` skips the call (CI cost). Default **on**.

UI: Fail “What happened” prefers `judge.why` when present; else the first Pass-lock reason. Do not show raw `confidence` as the only explanation.

The why-call uses **Responses pricing** (input $0.10 + output $0.50 / 1M), not Decisions input-only pricing.

---

## 6. Images (Decisions input)

Citation: [Decisions — Check an image](https://developers.openai.com/api/docs/guides/decisions): `input_image.image_url` must be a `data:image/png;base64,...` (or jpeg) data URL. **No** hosted HTTP/HTTPS URLs, **no** `file_id`. Combine `input_text` + `input_image` in a user message.

### 6.1 What we send

From the live workspace (and golden, if present), if `sniff_output_bytes` says `magic` in `{jpeg, png, gif}` (GIF is sniffed today; whether Decisions accepts GIF is **not** on the Decisions page — **hunch:** send JPEG/PNG only, the types in the official curl; skip GIF/PDF/webp unless Decisions later lists them):

- Read file bytes, base64, inline `data:{mime};base64,{b64}`
- Cap **product-side** (not an OpenAI Decisions number): omit a file larger than **4 MiB raw**, record `citations.omitted_images` with path + size, still score from text. Oversized image + text-only state often yields `Insufficient evidence` → Fail. That is acceptable fail-closed.
- Product cap **3** inline images per request (golden + actual + one extra fixture). Decisions does not publish an image-count limit. Do not cite the vision guide’s 1,500 / 512 MB as a Decisions fact — those are [Images and vision](https://developers.openai.com/api/docs/guides/images-vision) limits for Responses/Chat Completions.

**Size limits documented for Decisions:** none on the Decisions page. If OpenAI returns 400 for payload/image, surface that body (truncated), fail the check.

**Never:** fetch `https://...` image URLs from a skill prompt; never upload via Files API; never put base64 in logs.

PDFs stay text metadata (`path`, `present`, `kind`, `size`, optional extracted snippet already used for goldens). Do not pretend a PDF is an `input_image`.

### 6.2 Fallback Responses backend

The Responses vision guide **does** allow hosted URLs and `file_id`. **Do not use them** in the fallback either, so switching backends does not change image policy. Same inline data URLs.

---

## 7. Provider interface (callers stay stable)

```
engine._run_outcome_judge
        │
        ▼
Judge.judge(...)
        │
        ├── SkipJudge
        └── OutcomeJudge          # Pass lock + low-confidence warning + optional Fail why-call
                │
                └── JudgeBackend.evaluate(...)
                        ├── DecisionsBackend          # v1 default   POST /v1/decisions
                        └── StructuredOutputsBackend  # fallback     POST /v1/responses
```

### 7.1 Return dict (hosted-compatible + additive)

```python
{
  "status": "completed" | "skip" | "error",
  "provider": "skip" | "openai",
  "backend": "skip" | "decisions" | "responses",
  "display_name": "Built-in checker" | "OpenAI (your key)",
  "model": str | None,
  "passed": bool | None,
  "reasons": list[str],
  "why": str | None,                 # Responses follow-up; null if skipped/failed
  "answers": {cell: {choice, confidence, probabilities}},
  "soft_answers": {cell: {choice, confidence, probabilities}},
  "questions": <bank>,
  "soft_questions": <bank>,
  "cells": {cell: {label, choice, reason, confidence}},
  "citations": {"artifacts": [...], "omitted_images": [...]},
  "usage": dict | None,              # pass through if Decisions returns it; never invent
  "require_artifacts": bool,
  "blocks_deploy": True,
  "min_confidence": float,           # the threshold used
}
```

`SkipJudge` stays `{status: skip, passed: None, cells: []}`.

### 7.2 `JudgeBackend`

```python
class JudgeBackend(Protocol):
    name: str  # "decisions" | "responses"

    def evaluate(self, *, state, questions, timeout_sec: float) -> dict[str, Any]:
        """{status, model, answers, usage?, reason?} with per-name choice + optional
        confidence/probabilities. No secrets in logs."""
```

`DecisionsBackend` builds the six `choice` questions. `StructuredOutputsBackend` uses the enum JSON schema from the previous revision (same ordinals) so a key that cannot call Decisions can still score — **only when the operator sets the fallback**.

`OutcomeJudge` always runs `outcome_verdict` + fail-for-safety. Why-call is a method on `OutcomeJudge`, not on the backend (Decisions has nothing to explain).

### 7.3 How the provider is chosen

| Setting | Result |
| --- | --- |
| `SKILLGATE_JUDGE` unset/`auto`, no `OPENAI_API_KEY` | `SkipJudge` |
| `auto` + OpenAI key + live harness | `OutcomeJudge` + **Decisions** backend |
| `SKILLGATE_JUDGE=openai` + key + live | same; missing key → exit 2 |
| `SKILLGATE_JUDGE=openai` + demo | Skip (live-only) |
| `SKILLGATE_JUDGE=skip` | `SkipJudge` |
| `SKILLGATE_JUDGE_BACKEND=decisions` (default) | `/v1/decisions` |
| `SKILLGATE_JUDGE_BACKEND=responses` | Structured Outputs fallback (no auto-fallback on 403) |

`AI_GATEWAY_API_KEY` without `OPENAI_API_KEY` is **not** an OpenAI judge key.

---

## 8. Pass/Fail and engine wiring

Port into `skillgate_ai.judge_bank`: cell order, labels, criteria, `_PASS_LOCK`, `outcome_verdict`.

`engine._live_verdict`:

1. Skip / `passed is None` → det owns (built-in).
2. `status=completed` → `outcome_verdict`. Low Pass-lock confidence keeps Pass and stamps `warnings`.
3. `status=error` → fail closed.
4. `expect_skill is None` → det owns; judge stored as evidence.
5. Keep `expected_output_mismatch_reason`.

Then (not inside `_live_verdict`): if Failed, why-call; ignore its errors. Skip the why-call on a Pass that only has a low-confidence warning.

`gate.run_check` resolves judge and passes `judge=` into `run_eval`.

Timeout: 20s for Decisions (hosted judge used 20s), overridable `SKILLGATE_JUDGE_TIMEOUT_SEC`. Why-call: 10s, separate. Retry 429/502/503/504 up to 2 extra times. **Never retry 401/403/400.**

Transcript tail: 4000 characters.

---

## 9. File-by-file change list (Phase 2)

### 9.1 New

| Path | Role |
| --- | --- |
| `src/skillgate_ai/judge_bank.py` | Questions, labels, Pass lock, `outcome_verdict`. |
| `src/skillgate_ai/judge_openai.py` | `DecisionsBackend`, `StructuredOutputsBackend`, `OutcomeJudge` (fail-for-safety + why-call + image inlining). |
| `tests/test_judge_openai.py` | Mocked Decisions JSON (choice + probabilities + confidence), 401/403/404/400, timeout, missing answers, unknown choice, image data-URL construction, why-call skipped on Pass / ignored on error. |
| `tests/test_judge_bank.py` | Pass lock table + fail-for-safety table. |
| `docs/openai-judge.md` | User-facing: key, default Decisions scoring, fallback env, live smoke. |

### 9.2 Change

| Path | Change |
| --- | --- |
| `judge.py` | `resolve_judge`. |
| `engine.py` | §8 `_live_verdict`; pass `scores` and `path` into the judge (stop `del path`). |
| `gate.py` | Inject judge; stamp `config.judge` `{provider, backend, model}` (no secrets). |
| `config.py` | `SKILLGATE_JUDGE`, `SKILLGATE_JUDGE_BACKEND` (`decisions` default), `SKILLGATE_JUDGE_MODEL`, `SKILLGATE_JUDGE_TIMEOUT_SEC`, `SKILLGATE_JUDGE_MIN_CONFIDENCE`, `SKILLGATE_JUDGE_WHY`, `SKILLGATE_JUDGE_REASONING_EFFORT`. |
| `eval_config.py` | Fingerprint/label includes judge backend/model. |
| `errors.py` | `JudgeError` (exit 1). Explicit openai-without-key → `MissingLLMKeyError` (exit 2). |
| `report.py` | CLI/GitHub: who scored. Fail line can use `why`. |
| `local_ui/static/app.js` | Keys copy; “OpenAI (your key)” on the result panel; Fail why. **No** Checking-motion changes. |
| `local_ui/api.py` | Optional `judge_provider` on `/api/meta`. Never echo the key. |
| `.env.example` | OpenAI key scores live checks; backend/min-confidence comments. |
| `README.md`, `docs/quickstart.md`, `docs/ui.md` | Optional OpenAI scoring + Action `OPENAI_API_KEY` secret. |
| `pyproject.toml` | **0.4.0** on the implementation PR. |
| tests: `test_judge.py`, `test_gate.py`, `test_check_cli.py`, `test_local_ui.py`, `test_oss_surface.py` | As previously; plus no `jev`. |
| `.github/workflows/gate.yml` | Unchanged. No required OpenAI secret. |

### 9.3 Do not change

Docker `ENTRYPOINT`/`CMD`, pack schema, scorers, demo harness, deny-list.

### 9.4 Customer copy and errors

Use: “OpenAI (your key)”, “Built-in checker. This is not a live model.”, existing question labels. Avoid Jev / Decisions / `gpt-6-luna` in UI chrome (ids may appear in `--json`).

| Case | User message | Verdict |
| --- | --- | --- |
| 401 | OpenAI did not accept this API key. Check `OPENAI_API_KEY`. | Fail |
| 403 | OpenAI scoring is not enabled for this key. | Fail |
| 404 | OpenAI has no scoring endpoint for this key. | Fail |
| 400 (schema / image) | OpenAI rejected this scoring request. | Fail |
| 429 | OpenAI rate limit or quota. Wait and retry, or check billing. | Fail |
| timeout | OpenAI scoring timed out. | Fail |
| missing/invalid `choice` | OpenAI scoring returned an unusable answer. | Fail |
| why-call any error | (no extra message required) | **unchanged** |

Do **not** auto-retry Decisions 403 as Responses. Operator sets `SKILLGATE_JUDGE_BACKEND=responses`.

---

## 10. Test plan

### 10.1 Unit (CI, no real key)

Monkeypatch `httpx.post` (no new dep).

**Decisions (default):**

| Case | Assert |
| --- | --- |
| Request | URL ends with `/v1/decisions`; `model==gpt-6-luna`; six `choice` questions; names match the bank; `choices[].value` exact ordinals; Authorization present |
| Images | JPEG/PNG become `input_image` data URLs; no `http://`/`https://`/`file_id`; GIF/PDF not inlined (v1) |
| Happy path | All Pass ordinals + confidence `>= 0.5` → `passed is True`; `probabilities` round-trip into history-shaped dict |
| Fail lock | `Incorrect` → Fail; Path `Wasteful` does not Fail |
| Low confidence | `Correct` with `confidence: 0.2` → **Pass** + warning *The judge wasn't very sure about this one.* Exit unchanged |
| Missing confidence (Decisions, otherwise Pass) | **Pass** + same warning |
| Unknown `choice` | error, Fail |
| 401 / 403 / 404 / 400 / 429 / timeout | public message, Fail, no key in exception/logs |
| Why-call | On Fail, exactly one `/v1/responses`; `judge.why` set from schema; if why 500s, `passed` still False from Decisions |
| Why on Pass | no Responses call |
| Skip / demo / no key | no HTTP |
| `SKILLGATE_JUDGE=openai` without key | exit 2 |
| No-trigger | det owns |
| Fallback backend | `SKILLGATE_JUDGE_BACKEND=responses` hits `/v1/responses` with `json_schema` `strict: true`, not `/v1/decisions` |

### 10.2 Live smoke (documented, not CI)

```bash
export OPENAI_API_KEY=sk-...     # never echo
export SKILLGATE_JUDGE=openai
# default backend is decisions
# one-case temp pack recommended (this repo has no task filter)
skillgate check /tmp/one-case-pack --live --json
# assert tasks[].judge.backend == "decisions"
# assert tasks[].judge.answers.task_completion.choice
# assert "confidence" in that object
# exit 0 or 1, never a traceback
```

If the key returns **403** on `/v1/decisions`, that is a **failed smoke of the default backend**, not a reason to hide it. Document the fallback:

```bash
export SKILLGATE_JUDGE_BACKEND=responses
skillgate check /tmp/one-case-pack --live --json
```

Do not put a real key in GitHub Actions for merge.

---

## 11. Cost (official numbers; per-check is an estimate)

| Call | When | Official price | Notes |
| --- | --- | --- | --- |
| `POST /v1/decisions` | every live judged task | **$0.10 / 1M input**; no output/cache ([Decisions pricing](https://developers.openai.com/api/docs/guides/decisions)) | State + optional inlined images |
| `POST /v1/responses` why | Fail only (not low-confidence Pass) | Luna **$0.10 in / $0.50 out** per 1M ([model page](https://developers.openai.com/api/docs/models/gpt-6-luna)) | `max_output_tokens` 128 |
| Responses fallback scoring | only if backend=`responses` | same Luna in/out | six enums, no Decisions input-only rate |

**Hunch (not a measurement):** text-only Decisions on a 4k tail is cheap fractions of a cent; inlining a few-MB JPEG dominates input tokens. Why-call is small. Live smoke uses a **one-case** pack.

---

## 12. Private hosted app (`vigneshm1995personal/skillgate-ai`) via the published package

Facts: private `pyproject.toml` is still **0.2.0** in-tree (FastAPI, vault, `jev_qa`). Extract plan §9 pin has not landed.

After OSS **0.4.0** on PyPI:

1. Pin `skillgate-ai==0.4.0`.
2. Keep `jev_qa.py` as a `Judge` that POSTs Gateway `typesafe-ai/jev`. Import `judge_bank.outcome_verdict` from the wheel.
3. Hosted `resolve_judge`: explicit → else TypeSafe if `AI_GATEWAY_API_KEY` → else OpenAI Decisions if `OPENAI_API_KEY` → else hosted fail-closed (**hunch:** keep fail-closed for paid live; OSS skip stays public default).
4. Hosted judge card can show `why` + `confidence` without renaming chips.
5. Private CI `consume` job installs the pin.

This Phase 1 PR does **not** change the private repo.

---

## 13. Risks / unknowns (labeled)

| Item | Status | Mitigation |
| --- | --- | --- |
| Decisions public beta | Official as of 2026-10-07. Per-key 403 still possible. | Default Decisions; **no silent fallback**. Clear 403; documented `responses` backend. |
| Model id | **Verified:** `gpt-6-luna` only on Decisions. | Hard-require it on that URL. |
| Calibration vs TypeSafe | **Hunch:** same ordinals ≠ same calls. | Do not claim parity. |
| Confidence cutoff `0.5` | **Product choice.** OpenAI says use labeled examples; we have none. | Env override; keep Pass; plain warning; never change exit 0/1. |
| Path as `choice` not `score` | Justified from official type rule. | Revisit only with a new ordered rubric. |
| Decisions image size | **Undocumented** on the Decisions page. | Product 4 MiB / 3 images; fail closed on 400. Do not cite vision 512 MB as Decisions. |
| GIF / PDF as vision | Decisions examples are PNG (and talk about photos). | Inline JPEG/PNG only in v1. |
| Decisions `usage` field | Not in official excerpts. | Pass through if present; never invent. |
| `OPENAI_API_KEY` also selects live harness | Fact. | Copy: key is for live checks **and** scoring. |
| Why-call cost/latency | Extra Luna Responses on reds only. | `SKILLGATE_JUDGE_WHY=0`; 128 output tokens; must not change verdict. |

---

## 14. Ordered Phase 2 checklist

1. `judge_bank.py` + Pass lock / low-confidence warning tests.
2. `DecisionsBackend` + mocked `/v1/decisions` (probabilities, confidence, 403/400).
3. Image inlining (JPEG/PNG data URLs only).
4. Why-call on Fail; ignored errors.
5. `StructuredOutputsBackend` behind `SKILLGATE_JUDGE_BACKEND=responses`.
6. Wire `resolve_judge` → `run_check` → `run_eval`; no-trigger det.
7. CLI/UI “who scored” + Fail why. Motion tests still green.
8. Docs + live smoke. **Do not bump 0.4.0 in this PR** (follow-up).
9. **Private follow-up:** pin wheel; wrap Jev as `Judge`.

---

## 15. This PR

Phase 2 **code** on this branch (PR #8). Owner lock: low-confidence **keeps Pass** + warning; missing/invalid enum still fails closed.

- `judge_bank.py`, `judge_openai.py`, wiring in `judge.py` / `engine.py` / `gate.py` / `report.py` / UI
- User docs: `docs/openai-judge.md`
- Tests: mocked Decisions + Responses, including the low-confidence warning path
- **No** PyPI version bump (stays 0.3.0). **No** Docker/Action required secret.
