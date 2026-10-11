---
name: plan-mode
description: >-
  Use before any complex code change: research the codebase, list files and
  risks, get the plan approved before writing code.
---
# Plan mode (Feature Architect)

Before generating or modifying code for any non-trivial task:

1. Search the project to understand existing patterns, conventions, and the code paths involved.
2. Present a short implementation plan:
   - Files to create or modify (and why each).
   - Architectural considerations, breaking changes, migrations, risks.
   - How it will be tested and verified.
3. Wait for approval before executing. Do not touch files outside the plan without saying so.
