---
name: sample-skill
description: Write Conventional Commits messages from a short git diff. Use when the user pastes a diff, asks for a commit message, or wants a subject line like fix:, feat:, docs:, or refactor:.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1"
---

# Commit message writer

Read the diff in the task. **You** choose the Conventional Commits subject (one line). Do not use a template or canned message — summarize the real change.

## Message rules

- Format: `type: imperative summary` (lowercase type, no trailing period).
- Subject **≤ 72 characters**.
- Types: `fix` (bug), `feat` (new behavior), `docs` (documentation only), `refactor` (behavior-neutral code change).

## Save to `output/commit.txt`

### Gateway / `skillgate check --harness llm`

The harness only creates files when you emit a `RUN:` line that calls a bundled script. After you decide the subject, reply with **exactly one** line like:

```text
RUN: python3 .skillgate/skills/sample-skill/scripts/write_commit.py fix: handle empty cart total
```

Use your real subject in place of the example. The script only copies that text into `output/commit.txt` — it does not choose the message for you.

### Cursor / Codex / other agents

Write your subject line to `output/commit.txt` (create `output/` if needed). One line, no extra prose in the file.
