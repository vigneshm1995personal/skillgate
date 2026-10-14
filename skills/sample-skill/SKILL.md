---
name: sample-skill
description: Write Conventional Commits messages from a short git diff. Use when the user pastes a diff, asks for a commit message, or wants a subject line like fix:, feat:, docs:, or refactor:.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1"
---

# Commit message writer

Turn a small unified diff into **one** Conventional Commits subject line. The diff is in the task text (no binary fixtures).

## Required step (every task)

From the workspace root, run the bundled script. It reads `SKILLGATE_TASK` and writes the message file — **do not** paste the commit line only in chat.

```bash
python3 .skillgate/skills/sample-skill/scripts/agent_entry.py
```

The task names the output path (usually `output/commit.txt`). The script creates `output/` if needed.

## Message rules

- One line subject: `type: imperative summary` (lowercase type, no trailing period).
- Subject **≤ 72 characters**.
- Types: `fix` (bug), `feat` (new behavior), `docs` (documentation only), `refactor` (behavior-neutral code change).

Summarize the **main** change in the diff (function, module, or user-visible behavior).
