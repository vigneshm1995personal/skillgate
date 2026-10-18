---
name: readme-writer
description: Write a README in Markdown from a short project brief. Use when the user asks for a README with install steps and usage.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1"
---

# README writer

Turn a short brief into a README. Use only facts from the brief. If it has no license, write `not specified`. Do not invent one.

## How to work

```bash
python3 .skillgate/skills/readme-writer/scripts/agent_entry.py
```

The script reads the brief named in the task and writes the README path from the task.
