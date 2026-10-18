---
name: log-summarizer
description: Summarize application logs. Count errors and warnings and name each error code. Use when the user pastes a log or asks for a log summary.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1"
---

# Log summarizer

Count `ERROR` and `WARN` lines. List each `error=` code and how often it appears. Do not invent codes that are not in the log.

## How to work

```bash
python3 .skillgate/skills/log-summarizer/scripts/agent_entry.py
```

A log with no error or warning lines is `Errors: 0` and `Warnings: 0`.
