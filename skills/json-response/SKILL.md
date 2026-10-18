---
name: json-response
description: Reshape a JSON API response. Flatten nested fields to id, status, and total, and drop empty values. Use when the user has a JSON response.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1"
---

# JSON response

Reshape a JSON API body into a flat list. Do not invent fields. Drop values that are null or empty strings.

## How to work

Run the bundled script from the workspace root. It reads `SKILLGATE_TASK` and writes the file named in the task.

```bash
python3 .skillgate/skills/json-response/scripts/agent_entry.py
```

The script keeps `id`, `status`, and `total` from each object under `data`. An empty `data` array becomes `[]`.
