# Changelog

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
