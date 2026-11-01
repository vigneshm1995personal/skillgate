# Changelog

## Unreleased

## 0.7.14

- History, Gate, and `skillgate history show` now show enough of a run to screenshot: the case name or id (not the shared prompt), the case setup, a numeric score and written reason for each judge and text/log check with the source labeled (`from the log/text` / `from the judge` / `run facts`), plus a collapsible agent reply and every connector/tool call with arguments and response. Each check score is 0.00–1.00, higher is better (the outcome, not confidence); CLI and UI print the same Pass/Fail. A reason the judge wrote is labeled `from the judge`. Text built from the run (`Job result in the reply…`, `Tools used…`) is labeled `run facts`. A run with no written reason says `No reason recorded` without the judge label. Pass/fail does not read that stored reason. A green Passed run and a red Failed run do not show a stray `unsure, needs review`; that warning is only for a real low-confidence review. Every judge fail stays red. The rubric treats an honest pending / not-done / no-refund reply, when the task could not complete, as Correct, Fully followed, and a good result — never Incorrect, Violated, or Significant issues. Live check and `rescore` share one scorer that remaps a noisy quality/Violated row on those honest pending runs. When the pack asks for two refunds and only one succeeds, the gate is red from a deterministic count, even if the judge said Correct. A red c8 summary names the judge's Violated / Significant issues row, not the guard-retry warning. A guard-refused retry is WARNING (q0 Yes) and the summary matches that row. Failing rows do not say `Output matched what was expected.` Opening a History row — including a red run — shows that Gate result. `skillgate history show RUN --detail` prints the same; `--case NAME` filters to one case (unknown id exits 2). Secrets in replies and tool payloads are redacted. Older history files still render. The stale note `Wording check passed, so those Fail rows did not turn the gate red` is never shown.
- The no-duplicate-refund check counts refunds that succeeded, not attempts. A connector-refused retry (`409 lookup_required`) is a warning when a lookup shows only one refund went through: `A second refund attempt was refused. Only one refund went through.` Two succeeded refunds still fail. Until 0.7.14 is published, install from source.
- Live `skillgate check` and `skillgate rescore` call one scoring function. Passing log extras no longer clear a judge fail. **Incorrect**, **Partially completed**, **Violated**, and **Significant issues** stay red. A timeout whose refund went through counts as a success; timeout then a second succeeded refund is a duplicate fail. A guard-refused retry (`409 lookup_required`) is a WARNING, not PASS or FAIL. `skillgate rescore RUN --pack PATH` appends a new History row and matches CLI, JSON, and the UI (status/passed/scores). The stored reason is the judge's own words for that check. A red or green run does not keep `unsure, needs review` in JSON.

## 0.7.13

- A passing wording check no longer clears every judge fail. The override applies only when the reply is an honest rg4 negation (`not submitted yet` / `not yet`). Factual judge fails (wrong amount, false claims, a rewritten draft, a missing step) stay red even when the wording extra is Yes. Until 0.7.13 is published, install from source.

## 0.7.12

- When a skill states explicit banned phrases or required/forbidden wording, those lines are compiled into deterministic text checks on `output/reply.txt`. A hit fails the gate. The judge cannot override a passing or failing text check on that same wording rule. A judge fail that only restates a passing wording extra does not turn the gate red. Other judge verdicts (a rewritten draft, a wrong amount, a missing step, a false full-refund claim) still fail the gate. CLI, JSON, and the UI label that answer `from the log/text`, not `from the judge`. Write quoted lists (`Banned phrases:`, `Banned phrase:`, `Required wording:`, or `Nowhere in the reply use "…"`). Preview lists every compiled phrase (`skillgate judge show`, `skillgate checks show wording --pack`, or **Text checks from the skill**). Quoting the user, or a negation such as `has not been submitted` / `not yet submitted`, does not trip the check. A pending refund reply that says `I've submitted a full refund` or `submitted a full refund of USD 49.00` is red, including capitals, trailing punctuation, and a curly `’`. An honest pending reply that also says `USD 0.00` so far is green. A missing `reply.txt` fails with `reply.txt missing`. A cases.yaml missing `schema` or another required field exits 2 and names the field, without dumping the file. A second check while one is running exits 2. Until 0.7.12 is published, install from source.

## 0.7.11

- After majority voting, a blocking verdict whose confidence is still below 0.5 is **unsure, needs review**. It is not a gate fail (exit 0, `gate: needs review`, task `status: unsure`). Deploy stays pending. High-confidence fails still fail in one call. The pass mark is unchanged.
- Custom checks about log facts (tool-call counts and duplicates, whether a tool was called, what a tool returned) are scored from the spans when that is possible. The judge is used only when the check cannot be computed. A duplicate refund in the log still fails. CLI, JSON, and the UI say whether each custom check was computed from the log or by the judge.
- A sabotaged description cannot pass or land in review: skill trigger still requires a progressive-disclosure match, and a trigger miss fails the check even if the judge is green. A legitimate trigger — including a correct refusal such as `sql-writer` `edge-unknown-column`, or a long refund prompt — still counts when the description overlaps the request. The veto is a different-job description (no meaningful overlap), not a short-prompt ratio and not whether the output looks like a success. Followed the rules? is given the skill's rules and the run evidence so correct runs stay confident; a passing adherence choice with passing deterministic scorers is not marked review. An invalid extra-question `--id` is rejected (the question is not added). Predicate answers use `probability`, not `noul`.
- Log-fact polarity follows the ask: a bare "more than once?" is Yes when the log shows two or more calls; "at most once" / "no duplicate" / "Answer NO if more than once" is Yes when the count is one. File reads such as `status.txt` are counted from spans. The judge is not asked when the log can answer. The local UI renders `from the log` / `from the judge` on the opened check.
- An agent quota or usage-limit error (`ActionRequiredError`, "Weekly usage limit reached") is cannot-run (exit 2), not a quality red. A model or availability error (`Cannot use this model: composer-2.5`) is the same cannot-run exit 2, never a quality red.
- Example no-trigger prompts do not description-fit another installed example skill. `readme-writer` no longer uses "Count the warnings in a server trace." (that correctly picked `log-summarizer`). Any read inside the skill folder counts as a trigger, not only `SKILL.md`.
- Passing Pass-lock cells with passing scorers are not marked review. Custom checks about a timeout confirm, a claimed full refund, or a confirm without success are scored from the log plus workspace reply when that is computable. The local UI does not repeat built-in answers and does not sit on Loading… when status or checks are slow.
- CLI prints `NEEDS REVIEW` / `REVIEW`. JSON has `gate`, `tasks[].status`, `tasks[].review`, and `review_task_ids`. The local UI shows the same status. Until 0.7.11 is published, install from source.

## 0.7.10

- Built-in checks grade against the test's expected outcome. An honest escalation or refusal (refund impossible, tell the customer, write an owner report) is Fully completed, not unfinished.
- When a blocking answer's confidence is below 0.5, re-ask the judge up to 3 times and take the majority instead of failing on one unsure call. Custom checks and the pass mark are unchanged.
- Every red names the failing check and includes the judge's reason in the CLI and the UI.
- Low-confidence majority votes are recorded on the run as `tasks[].judge.votes` (`skillgate check --json`, `skillgate history show RUN --json`). `skillgate history show` prints the named red from a saved run with no agent. `--no-judge` still needs a signed-in agent.
- Docs: how to write an escalation or refusal expected outcome; where to read majority votes; how a red names the check. Until 0.7.10 is published, install from source.
- Scoring outages (including HTTP 500) are retried on a scored check. A 200 error envelope is a scoring failure, not a connected ping. `skillgate judge test` is a single probe. `--verbose` prints the sanitized upstream reason. A scoring outage is **not scored** in `--json` and history, not red or fail, and still exits 2. Low-confidence re-ask uses numeric confidence on blocking answers even when the provider flag was off. `skillgate history --pack` is documented.
- README install uses a venv or pipx, lists agent key names, maps Editor/Code/Terminal agent to Cursor / Claude Code / Codex and their skills folders, pipes `$OPENROUTER_API_KEY` into `JEV_API_KEY`, names the default OpenAI model `gpt-6-luna`, and clones before `docker compose`. The examples toast is `Installed 6 examples (53 files).`
- `skillgate compare versions --dry-run` with no refs prints a hint instead of an empty table.
- `skillgate judge provider show` with no decision model selected exits 2.

## 0.7.9

- A check that never starts is not saved. History, Home, and the heatmap do not show it as a failed scored run. A stored row with no result reads "not run" and "Not scored".
- `skillgate import` of a skill already in this project stops and leaves the files alone.
- A decision-model key is not an agent credential. `doctor` and `login --status` do not treat it as a Terminal agent API key. An `agent` binary that is not signed in is not "logged in".
- `skillgate judge provider show` and `set` print the option id, its model, and its base URL.
- Scoring errors do not include HTTP codes. A 404 or 405 from a non-scoring URL says the key is for a different endpoint. A Cloudflare 404 says that account id wasn't found. An account id that is not letters and digits has its own message. A chat model on a custom endpoint is refused.
- Settings clears the Test line when the option changes or on Save. Switch saves the decision model.
- `skillgate keys set` lists `JEV_API_KEY`, `CLOUDFLARE_API_TOKEN`, and `CUSTOM_DECISION_API_KEY`.
- `skillgate case remove` keeps the original checks of the bundled examples.
- `skillgate judge add-question` needs a skill pack.
- The Gate tab keeps the selected skill. A draft-only pack does not offer "Run 1 case". A missing expected-output file fails when the pack loads. `ingest` rejects a `cases.yaml` skill mismatch, and `check` reports a `SKILL.md` name mismatch before the no-agent error.
- `docker run` with no pack mounted exits 2. `skillgate example` writes `skills/NAME`. `--model CLEF` is stored as `clef`.
- Duplicate check ids use a plain sentence. `check --harness llm` and `byollm` exit 2.

## 0.7.8

- A decision model shows only the fields it scores with. OpenRouter (Jev) defaults to `https://openrouter.ai/api/v1` and `typesafe/jev-1.14`. OpenAI takes a key. Cloudflare takes an account id, `clef` or `clef-flash`, and a token. A custom endpoint takes a URL, a model, and a key.
- `skillgate judge provider set` rejects flags that option does not use. `skillgate judge test` reports a rejected key, the wrong endpoint, no credits, or a working model. A key prefix for another option says which command to switch to.
- The model list is a dropdown. An unknown model names the valid models and the option that accepts it.

## 0.7.7

- `skillgate examples list` and `skillgate examples install` copy dataset examples into `skills/`. Files already there stay as they are.
- Example skills: `json-response`, `json-response-sabotaged`, `readme-writer`, `log-summarizer`, `sql-writer`, and `receipt-extractor`. Each has fixtures, expected outputs, and an unrelated case. `json-response-sabotaged` fails the JSON checks.
- Skill Repository in the local UI lists those examples and installs them with the same skip rule.
- A short Writing a dataset section in the README points at `docs/writing-a-dataset.md`.

## 0.7.5

- Checks is split into agent setup, test cases, built-in checks, your checks, and the decision model. One Run sits at the bottom. Open a check to read the prompt the judge uses.
- Score live checks only with a decision model. Chat and Responses judges are removed, including auto selection and fallbacks. A live check with no decision model fails and asks you to pick one.
- Another System 1 endpoint can register on the same decision-model interface.
- The skill page Versions card counts and lists the same git refs as `skillgate compare versions`. `skillgate history` prints that list. Unrelated commits in the repo are not versions.
- Skip `.pydeps`, `pydeps`, and `__pypackages__` when collecting workspace files for a check.

## 0.7.4

- Add `output_optional: true` so Expected text is reference text for the judge and a missing or empty output file passes. A present file is still checked. Checks without the field stay required.

## 0.7.3

- Score a case's extra questions with Jev and with OpenAI Decisions. A failing answer fails the check, and What happened shows the question text plus the answer.

## 0.7.2

- Drop Claude `rate_limit_event` and system/init noise from rendered transcripts, judge evidence, and history. Tool use and tool result pairing stays.
- Show custom judge answers in `check_answers` (a Yes/No probability is no longer "Not available").
- Treat the reference output as an example of an acceptable answer. Grade against the case prompt and checks. `contains` substrings stay required.
- Ask every rubric question to cite a file and line, or a command. No violation in that evidence is not applicable or a pass.
- Save other files the agent created or changed in the workspace, with a size cap and a skip list (`node_modules`, `.git`, and similar), plus `git log` / `git diff` / `git status` when the workspace is a git repo.
- Run the Claude harness non-interactively inside the throwaway workspace (`--permission-mode acceptEdits`, `--permission-prompts none`, `--allowedTools` for Bash and file tools). Commands outside that workspace still need a prompt and are denied.
- `skillgate judge provider set` and `test` accept `--key-env`. `set` stores the env var name and does not store the key.
- The model picker lists the current Codex and Claude models from each harness. A custom model id is not an error.
- An Other judge stamp says "Scored by your judge".
- Workspace capture skips virtualenvs, caches, and `site-packages`, and caps how many files and bytes go to the judge. A rejected score names that payload size.
- Record the scoring endpoint that was actually used (Decisions API or Responses API) on the check JSON and in `judge provider test`.
- Treat Cursor "unable to fetch user details" as not signed in. Auth errors fail fast. A red check exits 1. `skillgate login cursor` says when Cursor is already signed in.
- `skillgate compare versions --git` accepts `--harness` and otherwise uses the harness from the skill's history runs.
- Git compare arms are saved on the pack's history, including the failure text.
- The task prompt no longer tells the agent to put files in `output/` when the task names another path.
- Trigger mode installs the skill without naming it in the prompt and records whether the agent loaded it.
- Codex checks keep `codex login` and do not need `CODEX_API_KEY`. Session flags turn off user and bundled skill discovery. Skill Gate does not set `CODEX_HOME` and does not read `auth.json`.
