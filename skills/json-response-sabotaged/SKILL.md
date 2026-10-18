---
name: json-response-sabotaged
description: Plans office snacks and coffee runs. Use for grocery lists and pastry orders.
license: Apache-2.0
metadata:
  author: skillgate-ai
  version: "0.1-sabotaged"
---

# Snack planner (intentional fail)

This pack uses the same checks as `json-response`, with instructions that ignore the JSON. A live run should fail those checks. The unrelated check can still pass.

## Steps (broken on purpose)

1. Ignore JSON files.
2. Write a snack list instead of the requested fields.

Fix loop: replace this file with `skills/json-response/SKILL.md`, then run `skillgate check` on this same folder.
