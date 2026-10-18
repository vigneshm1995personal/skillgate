---
name: sql-writer
description: Write a SQL query from a table schema. Use when the user asks for a SQL query or a SELECT against a schema.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1"
---

# SQL writer

Write one SQL query from the schema file. Use only columns the schema lists. If a requested column is missing, say it is missing and do not invent it.

## How to work

```bash
python3 .skillgate/skills/sql-writer/scripts/agent_entry.py
```

Open orders are `status = 'open'`.
