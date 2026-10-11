---
name: test-driven-vibe
description: >-
  Use when implementing logic: write a failing test first, implement until it
  passes, never weaken tests.
---
# Test-driven vibe (TDD iteration)

1. Write unit/integration tests covering the primary case and edge cases first.
2. Run the test command in the terminal and confirm they fail for the right reason.
3. Write the minimal implementation until all tests pass.
4. Run the full suite (and build/lint) before pushing.
5. Never change or delete test criteria to force a pass.
