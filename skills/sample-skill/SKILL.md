---
name: sample-skill
description: Write Conventional Commits messages from a short git diff. Use when the user pastes a diff, asks for a commit message, or wants a subject line like fix:, feat:, docs:, or refactor:.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1"
---

# Commit message writer

Turn a small unified diff into **one** Conventional Commits line (optional body later). The user’s diff is in the task text — there are no binary fixtures.

## Output

1. Create `output/` if needed.
2. Write **only** the commit message to `output/commit.txt`.
3. First line = subject: `type: imperative summary` (lowercase type, no trailing period).
4. Keep the subject **≤ 72 characters**.
5. Pick the type from the change:
   - `fix` — bug fix
   - `feat` — new behavior
   - `docs` — documentation only
   - `refactor` — behavior-neutral code change

## How to work

Read the diff in the task. Summarize the **main** user-visible change in the subject. Mention the touched area (function, module, or feature) when it helps.

Optional helper (demo harness): `python3 .skillgate/skills/sample-skill/scripts/agent_entry.py` reads `SKILLGATE_TASK` and writes `output/commit.txt`.
