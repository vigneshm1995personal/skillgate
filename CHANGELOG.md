# Changelog

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
