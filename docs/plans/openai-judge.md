# OpenAI judge provider — Implementation Plan

> **This document is Phase 1 (plan only) for OSS `vigneshm1995personal/skillgate`.** Do **not** implement the OpenAI judge, cell bank, UI copy, or tests in this PR. Do **not** copy private `jev_qa.py` into this repo. Do **not** flip this repo public.

**Goal:** Let a user score live checks with **their own OpenAI API key**, answering the same fixed questions the hosted TypeSafe judge answers today, with the same Pass/Fail lock and the same report shape. The rest of the gate (`skillgate check` exit 0/1, history JSONL, Docker `ENTRYPOINT`/`CMD`, copy-paste GitHub Action) stays unchanged.

**Parent (locked):** [`docs/plans/2026-10-03-skillgate-oss-extract.md`](2026-10-03-skillgate-oss-extract.md). Decision rule unchanged: if a feature cannot work as **one pack on disk** plus `skillgate check` exiting **0 or 1** with **no Skill Gate account**, it does not belong here. OpenAI judge = the user’s key only. The built-in checker stays the skip/fallback when no OpenAI key is set.

Inspected OSS tree: `main` @ `6a3b0d3` (`Hold Checking then draw Passed or Failed on Run live (#7)`). PyPI dist **`skillgate-ai` 0.3.0**. CLI command **`skillgate`**. Hosted app stays private at [`vigneshm1995personal/skillgate-ai`](https://github.com/vigneshm1995personal/skillgate-ai).

Private judge source of truth (read-only, **do not copy the file**): `src/skillgate_ai/jev_qa.py` on private `skillgate-ai` (`run_jev_outcome_judge`, `CHECK_CELL_ORDER`, `_PASS_LOCK`, `SOFT_CELL_ORDER`). Hosted engine still hard-calls Jev (`run_jev_outcome_judge` inside private `engine._run_outcome_judge`); OSS already stripped that import.

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

Full choice lists (must be the schema enums):

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
4. Same questions, same Pass lock, same `tasks[].judge` shape as hosted TypeSafe, so history / `check` / Docker / Action stay compatible.
5. Customer copy is plain. Do **not** show “Jev”, “Jev cells”, “harness”, “BYOLLM”, “Option A” unless already user-facing (hosted may say TypeSafe internally; OSS UI already forbids `jev` in `test_ui_copy_has_no_internal_jargon`).
6. Reuse Checking → slide → drawn Passed/Failed. No new hold screen, no “Evaluating”.
7. Errors (bad key, quota, model missing, Decisions 403, timeout, refusal) → clear message, **fail the check**, never silent Pass, never a traceback as the primary UX.
8. Do not add `openai` as a required PyPI dep. Use existing `httpx` (same as BYO chat). Optional extra is allowed later; v1 should not need it.
9. Do not import or vendor `jev_qa.py`. Re-home the **cell bank + Pass lock** in OSS under a public name (`skillgate_ai.judge_bank`), then private TypeSafe imports that bank from the wheel.
10. Implementation PR bumps package version **0.3.0 → 0.4.0** (this plan PR does not).

---

## 2. OpenAI: what is verified vs what we will not depend on yet

Verified **2026-10-07** against official OpenAI docs (not blogs).

### 2.1 Model id — verified

**Default model: `gpt-6-luna`.**

Citation: [GPT-6 Luna model page](https://developers.openai.com/api/docs/models/gpt-6-luna) and [Models catalog](https://developers.openai.com/api/docs/models).

Facts from those pages:

- Request id is `gpt-6-luna` (not “GPT-6 Luna”).
- Structured outputs: **Supported**.
- Endpoints include Chat Completions `v1/chat/completions` and Responses `v1/responses`.
- `reasoning.effort` supports `none`, `low`, `medium` (default), `high`, `xhigh`, `max`.
- Chat Completions function calling only with `reasoning_effort: "none"`. Judge v1 does **not** use tools.
- Context 1.05M, max output 128K, knowledge cutoff May 18, 2026.
- Standard (non-Decisions) pricing: **$0.10 / 1M input**, **$0.50 / 1M output** tokens. Cached input $0.01; cache writes $0.125. Long-context (>272K input) multipliers apply. Regional processing +10% where available.

**Config, not a hardcoded-only id:** `SKILLGATE_JUDGE_MODEL` (default `gpt-6-luna`). If OpenAI ships a snapshot id later, operators can override without a code change.

### 2.2 Decisions API — official docs exist; still not the v1 path

Citation: [Decisions guide](https://developers.openai.com/api/docs/guides/decisions).

Official page (fetched 2026-10-07) says:

- `POST https://api.openai.com/v1/decisions`
- Public beta; GA “in the coming weeks”
- Only model: `gpt-6-luna`
- Body: `{model, input, questions[]}` with `predicate` | `choice` | `score`
- Choice answer: `{type, name, choice, probabilities[], confidence}`
- Decisions-only pricing: **$0.10 / 1M input**, no output / cache charges (different from ordinary Luna requests)

**Product lock for v1:** do **not** call `/v1/decisions` by default.

Why, even though the schema is now on the official page:

- Owner instruction for this work: ship on the normal API + Structured Outputs so any standard `OPENAI_API_KEY` works.
- Earlier (through at least 2026-10-02, third-party) standard keys returned HTTP **403** `Decision API is not enabled for this user`. That may still be true for some accounts during public beta. Treat enablement as **unknown per key**.
- No first-party Python SDK method is a published dependency of this repo. (Hunch: Node `client.decisions.create` is landing in `openai/openai-node` PR #2886; do not rely on it.)

Phase 2 therefore implements **Structured Outputs now**, and a `JudgeBackend` so a future `decisions` backend can replace **one HTTP call** without touching `engine` / `gate` / UI.

If someone sets `SKILLGATE_JUDGE_BACKEND=decisions` later: same questions as `choice` items; HTTP 403 must surface as “OpenAI scoring is not enabled for this key” (or similar), fail the check, never Pass.

### 2.3 Structured Outputs — verified request/response (v1 backend)

Citation: [Structured model outputs](https://developers.openai.com/api/docs/guides/structured-outputs) (Responses mode). Official curl uses `POST /v1/responses` with `text.format` `{type: json_schema, name, schema, strict: true}`. Enums are a documented schema feature. Refusals arrive as `output[].content[]` with `type: "refusal"` (not schema JSON) — fail closed.

**v1 HTTP call (httpx, no SDK required):**

`POST https://api.openai.com/v1/responses`

```json
{
  "model": "gpt-6-luna",
  "reasoning": {"effort": "low"},
  "input": [
    {"role": "system", "content": "<fixed scorer instructions + ordinal definitions>"},
    {"role": "user", "content": "<JSON state: check prompt, expect/selected skill, scorer rows, artifacts, golden/actual, path, transcript tail>"}
  ],
  "text": {
    "format": {
      "type": "json_schema",
      "name": "skill_gate_check",
      "strict": true,
      "schema": {
        "type": "object",
        "properties": {
          "task_completion": {
            "type": "string",
            "enum": ["Fully completed", "Partially completed", "Not completed"]
          },
          "correctness": {
            "type": "string",
            "enum": ["Correct", "Mostly correct", "Incorrect", "Insufficient evidence"]
          },
          "instruction_adherence": {
            "type": "string",
            "enum": ["Fully followed", "Minor deviation", "Major deviation", "Violated"]
          },
          "evidence_action_validity": {
            "type": "string",
            "enum": ["Fully supported", "Partially supported", "Unsupported", "N/A"]
          },
          "result_quality": {
            "type": "string",
            "enum": ["Clear and complete", "Mostly good", "Significant issues", "Poor"]
          },
          "path_efficiency": {
            "type": "string",
            "enum": ["Efficient", "Acceptable", "Looping", "Wasteful"]
          }
        },
        "required": [
          "task_completion",
          "correctness",
          "instruction_adherence",
          "evidence_action_validity",
          "result_quality",
          "path_efficiency"
        ],
        "additionalProperties": false
      }
    }
  }
}
```

Notes that are documented, not hunches:

- Every object property must be in `required`; `additionalProperties` must be `false` (Structured Outputs subset).
- Auth: `Authorization: Bearer $OPENAI_API_KEY`. Never write that value into logs; on HTTP errors log **status + truncated body** only (same pattern as private `_http_error_detail`).
- Parse success from `output_text` / `output[].content[]` `output_text`. If any content part is `refusal` → `status=error`, fail the check.
- `reasoning.effort: "low"` is a **supported** Luna value. Default on the model page is `medium`. Using `low` is a product choice for latency/cost on a constrained enum task, **not** a documented “judge mode”. Make it `SKILLGATE_JUDGE_REASONING_EFFORT` (default `low`). `none` is also supported on Luna if we need to cut reasoning tokens later.

Chat Completions equivalent (documented; keep as a fallback only if Responses is awkward in tests): `POST /v1/chat/completions` with `response_format: {type: "json_schema", json_schema: {name, strict: true, schema}}`. Prefer Responses for v1 because the Structured Outputs guide’s Responses examples are the current canonical shape, and Luna’s model page lists Responses as a first-class endpoint.

**Do not invent** Decisions rate limits, a Python `client.decisions.create` in this package, or unpublished snapshot ids.

---

## 3. Provider interface (callers stay stable)

Keep `Judge` as the only type `engine` knows. Split “who scores” from “which HTTP”.

```
engine._run_outcome_judge
        │
        ▼
Judge.judge(goal, artifacts, transcript_tail, **state)
        │
        ├── SkipJudge                # no HTTP; passed=None
        └── OutcomeJudge             # shared Pass lock + cell stamp
                │
                └── JudgeBackend.evaluate(state, questions) -> raw answers
                        ├── StructuredOutputsBackend   # v1 default  POST /v1/responses
                        └── DecisionsBackend           # future       POST /v1/decisions
```

### 3.1 `Judge` (existing, slightly documented)

Return dict (hosted-compatible):

```python
{
  "status": "completed" | "skip" | "error",
  "provider": "skip" | "openai",          # new, stable
  "backend": "skip" | "structured" | "decisions",
  "display_name": "Built-in checker" | "OpenAI (your key)",
  "model": str | None,
  "passed": bool | None,                 # None only for skip
  "reasons": list[str],
  "answers": {cell: {"choice": str}},    # Pass-lock cells
  "soft_answers": {cell: {"choice": str}},
  "questions": <bank>,
  "soft_questions": <bank>,
  "cells": {cell: {"label", "choice", "reason"}},  # dict, hosted shape
  "citations": {"artifacts": [...]},
  "usage": dict | None,                  # pass through; never invent
  "require_artifacts": bool,
  "blocks_deploy": True,                 # when this judge owned the verdict
}
```

`SkipJudge` stays `{status: skip, passed: None, cells: []}` so `tests/test_judge.py` remains valid. UI/CLI treat skip as “Built-in checker”.

### 3.2 `JudgeBackend` (new, small)

```python
class JudgeBackend(Protocol):
    name: str  # "structured" | "decisions"

    def evaluate(
        self,
        *,
        state: Mapping[str, Any],
        questions: Mapping[str, Any],
        timeout_sec: float,
    ) -> dict[str, Any]:
        """Return {status, model, answers, usage, reason?} with answers[key].choice.

        Must not log secrets. HTTP 4xx/5xx become status=error with a public reason.
        """
```

`OutcomeJudge` maps each bank key from `evaluate()` into hosted-shaped `answers` / `soft_answers`, then runs **the same** `outcome_verdict` as TypeSafe.

Future `DecisionsBackend.evaluate`: one `POST /v1/decisions` with `questions[].type = "choice"`, `choices[].value` = the ordinals above, `name` = cell key, `instructions` = user-facing label + criteria text. Map `answers[].choice` back onto the bank. Callers unchanged.

### 3.3 How the provider is chosen

Resolved once per `run_check`, passed into `run_eval(..., judge=...)`.

| `SKILLGATE_JUDGE` | Key present | Result |
| --- | --- | --- |
| unset / `auto` | no `OPENAI_API_KEY` | `SkipJudge` (built-in) |
| unset / `auto` | `OPENAI_API_KEY` set **and** live harness | `OutcomeJudge` + structured backend |
| `openai` | key set, live harness | OpenAI judge (error if key missing **before** the run: exit 2, same family as missing live key) |
| `openai` | demo / `--demo` | still Skip (judge is live-only, same as hosted) |
| `skip` | any | `SkipJudge` |
| `decisions` | (Phase 2.1+, not default) | Decisions backend; 403 fail-closed |

`SKILLGATE_JUDGE_BACKEND=structured|decisions` defaults to `structured`. `decisions` is documented but **not** wired until a follow-up unless implementation is cheap behind the protocol (prefer a clearly skipped/unimplemented backend in v1 that errors with “not enabled in this version” rather than a silent structured fallback).

Harness vs judge:

- Demo / no live key → no OpenAI judge call.
- Live Cursor + OpenAI key → Cursor runs the skill; OpenAI scores it.
- Live Codex/llm with only `OPENAI_API_KEY` → same key runs and scores.
- `AI_GATEWAY_API_KEY` without `OPENAI_API_KEY` → **not** an OpenAI judge key in OSS (that is hosted TypeSafe / BYO chat). Auto does not treat Gateway as OpenAI scoring.

Explicit setting always wins over auto.

---

## 4. Pass/Fail and engine wiring

Port these into OSS `skillgate_ai.judge_bank` (names can match private constants so the hosted wrapper is a thin import):

- `CHECK_CELL_ORDER`, `CHECK_CELL_LABELS`, `_OUTCOME_QUESTIONS`
- `SOFT_CELL_ORDER`, `SOFT_CELL_LABELS`, `_SOFT_OUTCOME_QUESTIONS`
- `_PASS_LOCK`, `_PASS_NEED_LABEL`
- `outcome_verdict`, `has_option_a_cells`, criteria lookup

`engine._live_verdict` changes (behavior, not a new product):

1. **Skip / `passed is None`:** det owns (unchanged OSS). This is the built-in checker.
2. **Live judge `status=completed`:** apply `outcome_verdict` (do not trust a raw model bool). Stamp `passed` / `reasons`.
3. **Live judge `status=error`:** fail closed with the public reason. Never Pass.
4. **`expect_skill is None`:** det owns; judge payload still stored as evidence (match hosted). **Today OSS does not do this** — adding it is required so OpenAI cannot red a clean no-trigger skip.
5. Keep `expected_output_mismatch_reason` (JPEG-as-JSON etc.) as an extra fail.

Do not call the judge on demo. Do not change `is_live_harness`.

`gate.run_check` must `load_env`, `get_llm_config`, `resolve_judge(cfg, harness_name)`, pass `judge=` into `run_eval`.

Timeout: 20s per task (hosted `DEFAULT_JUDGE_TIMEOUT_SEC`), overridable via `SKILLGATE_JUDGE_TIMEOUT_SEC`. Retry **once or twice** on 429/502/503/504 with short backoff (hosted retries 3 times). Never retry 401/403.

Transcript tail: 4000 characters (hosted `JUDGE_TRANSCRIPT_TAIL_CHARS`).

---

## 5. File-by-file change list (Phase 2)

### 5.1 New

| Path | Role |
| --- | --- |
| `src/skillgate_ai/judge_bank.py` | Fixed questions, labels, Pass lock, `outcome_verdict`. No HTTP. Private TypeSafe will import this from the wheel. |
| `src/skillgate_ai/judge_openai.py` | `StructuredOutputsBackend` + `OutcomeJudge` factory. httpx only. Error mapping. |
| `tests/test_judge_openai.py` | Mocked httpx: schema body, enum-only parse, 401/403/429, timeout, refusal, missing fields, no silent Pass. |
| `tests/test_judge_bank.py` | Pass lock table (Fully completed+Correct+… → Pass; soft result_quality; path_efficiency ignored). |
| `docs/openai-judge.md` | User-facing: set `OPENAI_API_KEY`, what gets scored, live smoke command. No internal lingo. |

### 5.2 Change

| Path | Change |
| --- | --- |
| `src/skillgate_ai/judge.py` | Keep protocol + `SkipJudge`. Add `resolve_judge(cfg, *, harness: str) -> Judge`. Optional `provider` / `display_name` on skip payload. |
| `src/skillgate_ai/engine.py` | `_live_verdict` as §4. Continue calling `Judge.judge` with today’s kwargs (`expect_skill`, `selected_skill`, `golden`, `actual_output`, plus **pass `scores` and `path`** — hosted already sends them; OSS currently `del`s `path`). |
| `src/skillgate_ai/gate.py` | Resolve judge; pass into `run_eval`. Stamp `report.config["judge"]` = `{provider, backend, model}` (no secrets). |
| `src/skillgate_ai/config.py` | Read `SKILLGATE_JUDGE`, `SKILLGATE_JUDGE_BACKEND`, `SKILLGATE_JUDGE_MODEL`, `SKILLGATE_JUDGE_TIMEOUT_SEC`, `SKILLGATE_JUDGE_REASONING_EFFORT`. Do not put keys in `__repr__`. Hints: OpenAI key scores live checks; skip = built-in. |
| `src/skillgate_ai/eval_config.py` | Include judge provider/model in fingerprint/label when set, so history can tell “OpenAI scored this” vs built-in. |
| `src/skillgate_ai/errors.py` | `JudgeError(SkillGateError)` for fail-closed scoring (exit 1, not 2). Missing **explicit** `SKILLGATE_JUDGE=openai` without a key can reuse `MissingLLMKeyError` (exit 2). |
| `src/skillgate_ai/report.py` | `format_cli` / `format_github`: one line naming who scored (`OpenAI (your key)` / `Built-in checker`). Do not dump cell keys. |
| `src/skillgate_ai/local_ui/static/app.js` | Keys-step copy: OpenAI key also scores live checks. Result panel: show `display_name` under Passed/Failed (reuse `checkerLabel` or a sibling line). **Do not** change Checking hold / slide / `check-pop` drawing. Keep two-step Local → Key wizard. |
| `src/skillgate_ai/local_ui/static/index.html` | Only if a static string needs the same sentence (likely no). |
| `src/skillgate_ai/local_ui/api.py` | Env allow-list already has `OPENAI_API_KEY`. Optionally return `has_openai_key` / `judge_provider` on `/api/meta` so the UI can label without guessing. Never echo the key. |
| `.env.example` | Comment block: OpenAI key for live run **and** scoring; `SKILLGATE_JUDGE=auto\|openai\|skip`. |
| `README.md`, `docs/quickstart.md`, `docs/ui.md` | Optional OpenAI scoring; Action snippet with `env: OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}` as optional. Det path still needs no secret. |
| `pyproject.toml` | Version **0.4.0** on the implementation PR. No new required deps. |
| `tests/test_judge.py` | SkipJudge unchanged. |
| `tests/test_gate.py` / `test_check_cli.py` | Auto + OpenAI key still goes live for the **harness**; assert judge is resolved (mock HTTP so CI has no real key). Demo / no key still exit 0/1 on pdf twins. |
| `tests/test_local_ui.py` | Copy assertions: OpenAI field remains; no `jev`; Checking motion tests still pass; new friendly “who scored” string present. |
| `tests/test_oss_surface.py` | Still forbids `jev_qa`. Allow `judge_openai` / `judge_bank`. |
| `.github/workflows/gate.yml` | Unchanged (det). Do **not** add `OPENAI_API_KEY` as a required secret. |

### 5.3 Do not change

- Docker `ENTRYPOINT`/`CMD`, `compose.yaml`
- Pack schema, scorers, demo harness
- Deny-list / extract script
- Hosted `web/` (not in this repo)

### 5.4 Customer-facing copy (locked tone)

Use:

- “OpenAI (your key)” / “Scored by OpenAI with your key”
- “Built-in checker. This is not a live model.” (already shipped)
- Question labels: Got the job done? / Got it right? / Followed the rules? / Used the right evidence/actions? / Delivered a good result? / Path

Avoid in UI/CLI:

- Jev, TypeSafe, cells, harness, BYOLLM, Option A, `task_completion` as a heading, Decisions API, `gpt-6-luna` as a required user-facing term (model id may appear in `--json` / config label only)

Errors (examples; keep short):

| HTTP / case | User message |
| --- | --- |
| 401 | OpenAI did not accept this API key. Check `OPENAI_API_KEY`. |
| 403 | OpenAI refused this request. This key may not have access (including Decisions, if that backend is on). |
| 429 | OpenAI rate limit or quota. Wait and retry, or check billing. |
| 404 / model missing | This OpenAI model is not available for your key (`gpt-6-luna` unless overridden). |
| timeout | OpenAI scoring timed out. |
| refusal | OpenAI declined to score this check. |
| bad JSON / missing enum | OpenAI scoring returned an unusable answer. |

All of the above → check **Failed**, gate red, exit 1.

---

## 6. Test plan

### 6.1 Unit (CI, no real key)

`tests/test_judge_openai.py` with `httpx.MockTransport` or `respx` **only if we add it** — prefer stdlib monkeypatch of `httpx.post` to avoid a new dep.

| Case | Assert |
| --- | --- |
| Request body | `model==gpt-6-luna` (or config), `text.format.type==json_schema`, `strict is True`, every cell in `enum`, `additionalProperties is False`, all six keys `required` |
| Happy path | Enums map to `answers`/`soft_answers`; Pass lock Pass; `cells` dict uses **labels** not raw keys |
| Fail lock | e.g. `Incorrect` → `passed is False`, reason mentions “Got it right?” not `correctness` in UI layer (internal reasons may keep the key for hosted parity — **hunch:** keep hosted reason format `Checks: correctness Incorrect (need Correct)` in JSON, map to labels only in UI/CLI) |
| Extra / unknown enum | Treat as fail closed (schema should prevent; still guard) |
| Refusal content type | `status=error`, `passed=False` |
| 401 / 403 / 429 | Public message, no stack in `JudgeError.message`, `passed=False` |
| Timeout (`httpx.TimeoutException`) | same |
| Decisions 403 body | Dedicated message even on structured backend if body mentions Decision API |
| Authorization header | Present on the request; **absent** from logs / exception strings / returned dict |
| Skip without key | `resolve_judge` → SkipJudge; `_live_verdict` leaves det in charge |
| `SKILLGATE_JUDGE=openai` without key | exit 2 / `MissingLLMKeyError`, no silent Pass |
| Demo harness | no HTTP |
| No-trigger (`expect_skill is None`) | det owns even if OpenAI says Not completed |

`tests/test_judge_bank.py`: table-driven Pass lock including soft `result_quality` and ignored `path_efficiency`.

Existing pdf / sabotaged / UI motion tests must stay green with no keys.

### 6.2 Live smoke (documented, not CI)

Not in `.github/workflows/gate.yml`. Operator machine or a manual workflow_dispatch later.

```bash
# from a pack directory, with a real key in the environment (not committed)
export OPENAI_API_KEY=sk-...          # never echo / never printenv in logs
export SKILLGATE_JUDGE=openai
skillgate check skills/pdf --live --json | python -c \
  'import json,sys; r=json.load(sys.stdin); t=r["tasks"][0]; j=t["judge"];
   assert j["status"]=="completed" and j["provider"]=="openai";
   print(r["gate"], j["display_name"], j["model"])'
# expect: green or red from the Pass lock; never a traceback
echo $?   # 0 or 1
```

Cheaper smoke (one case): document `SKILLGATE_TASK_FILTER` **only if it already exists** — it does **not**. Do not invent a filter in this plan. Smoke = full `skills/pdf` live run (8 tasks) **or** a tiny throwaway pack in `/tmp` with one trigger-only case. Prefer a **one-case temp pack** in the smoke doc so a real key is not billed 8×.

Record: HTTP must hit `api.openai.com`; judge `model` echoes `gpt-6-luna` unless overridden.

If the live key gets Decisions 403, that is **out of scope for v1 smoke** (we are not calling `/v1/decisions`).

---

## 7. Private hosted app (`vigneshm1995personal/skillgate-ai`) via the published package

Facts: private `pyproject.toml` is still **0.2.0** with the full in-tree `src/skillgate_ai` (FastAPI, vault, `jev_qa`). Extract plan §9 is the follow-up: pin `skillgate-ai==X.Y.Z` from PyPI and inject the Judge. That pin has **not** landed. Until it does, private continues to vendor engine/Jev.

After OSS **0.4.0** is on PyPI:

1. Private adds `skillgate-ai==0.4.0` (Dependabot pin, no unbounded `>=`).
2. Delete in-tree copies of `judge_bank` / engine judge protocol as they are replaced by the wheel. **Keep** `jev_qa.py` as a `Judge` implementation that POSTs `https://ai-gateway.vercel.sh/v1/evaluate` with model `typesafe-ai/jev`.
3. Private `run_jev_outcome_judge` should call `judge_bank.outcome_verdict` so Pass lock cannot drift.
4. Private `engine._run_outcome_judge` should take `Judge` like OSS (it does not today). Hosted `resolve_judge`:
   - explicit setting if any
   - else TypeSafe when `AI_GATEWAY_API_KEY` is set (current product)
   - else OpenAI when `OPENAI_API_KEY` is set (new, same as OSS)
   - else hosted fail-closed **or** skip — **hunch:** keep hosted fail-closed without TypeSafe for paying live runs; OSS skip remains the public default
5. Hosted UI may keep its existing judge card; it already consumes `answers` / `cells` / `passed`. OSS `display_name` / `provider` let it show “OpenAI (your key)” vs TypeSafe without saying “Jev cells”.
6. Private CI `consume` job installs the pin and runs hosted tests.

This Phase 1 PR does **not** change the private repo.

---

## 8. Risks / unknowns (labeled)

| Item | Status | Mitigation |
| --- | --- | --- |
| Decisions not GA / per-key 403 | Official docs: public beta as of 2026-10-07. Enablement for a **standard** key is still unverified in this repo. | v1 = Structured Outputs only. Decisions behind an explicit backend later; 403 fail-closed with a plain message. |
| Model id | **Verified:** `gpt-6-luna`. | Config override `SKILLGATE_JUDGE_MODEL`. |
| Calibration vs TypeSafe | **Hunch:** same questions + lock ≠ same ordinals. Luna is a generative model with constrained decoding; TypeSafe Jev is a dedicated evaluate endpoint. Scores will diverge on edge traces (invented JSON, looping tools). | Do not claim “same as hosted.” Ship the lock; add a later side-by-side eval if the owner wants it. |
| `reasoning.effort: low` vs `medium` | Supported values; quality impact **unverified**. | Config; default `low`; document. |
| Responses vs Chat Completions | Both listed on the Luna page; Structured Outputs guide’s Responses curl is the v1 shape. | Implement Responses; Chat Completions only if Responses parse is painful. |
| OSS `_live_verdict` vs hosted no-trigger exception | Fact: they differ today. | Align when a live judge is present (§4.4). |
| `OPENAI_API_KEY` also selects live Codex/llm | Fact: `run_check` auto-live when any key is set. Adding a judge key can switch a user from built-in to **live harness** as well as scoring. | Copy must say the OpenAI key is for live checks **and** scoring. `SKILLGATE_JUDGE=skip` still runs live if a harness key exists. `--demo` / Skip in the wizard stays the built-in path. |
| Hosted still in-tree | Fact: no PyPI pin yet. | §7 follow-up; OSS is usable without it. |
| Cost | Luna standard: $0.10 / $0.50 per 1M in/out ([model page](https://developers.openai.com/api/docs/models/gpt-6-luna)). Per-check cost **unverified**. | One Responses call per live task; 4k transcript tail; live smoke uses a one-case pack. |
| Key leakage | Tests must assert the secret never appears in exceptions, history JSON, or UI payloads. | Truncate error bodies; never `print` env. |

---

## 9. Ordered Phase 2 checklist

1. Add `judge_bank.py` + `test_judge_bank.py` (Pass lock only; no HTTP).
2. Add `JudgeBackend` + `StructuredOutputsBackend` + mocked `test_judge_openai.py`.
3. Wire `resolve_judge` → `gate.run_check` → `run_eval`; fix `_live_verdict` (error fail-closed, no-trigger det).
4. CLI/GitHub/UI “who scored” + keys-step copy. Re-run UI motion tests.
5. Docs: `.env.example`, `docs/openai-judge.md` live smoke, README/quickstart optional Action env.
6. Bump **0.4.0**. `pytest -q` green without `OPENAI_API_KEY`.
7. Manual live smoke with a real key (one-case pack).
8. **Private follow-up (separate repo):** pin `skillgate-ai==0.4.0`, wrap Jev as `Judge`, import `judge_bank`.

---

## 10. This PR

Docs only:

- `docs/plans/openai-judge.md` (this file)
- `README.md` pointer in the docs list

No product code, no version bump, no Docker/Action change.
