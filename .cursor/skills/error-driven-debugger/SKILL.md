---
name: error-driven-debugger
description: >-
  Use when diagnosing bugs or errors: root cause first, then a targeted fix
  verified by tests.
---
# Error-driven debugger

1. Do not apply quick hotfixes without root-cause analysis.
2. Form hypotheses; check runtime logs, state, and trace the execution path from the stack trace.
3. Explain why the failure occurred, based on the call stack and state.
4. Make a targeted fix and add a regression test.
5. Verify by running the build/test script; confirm the original symptom is gone.
