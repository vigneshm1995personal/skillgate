import { describe, expect, it } from "vitest"

import { resolvedHarnessName } from "./types"

describe("resolvedHarnessName", () => {
  it("does not invent Cursor when Auto has nothing to run", () => {
    expect(resolvedHarnessName("auto")).toBe("auto")
    expect(resolvedHarnessName("auto", null)).toBe("auto")
    expect(resolvedHarnessName("auto", { default_harness: "auto" })).toBe("auto")
    expect(resolvedHarnessName("auto", { default_harness: "llm" })).toBe("llm")
    expect(resolvedHarnessName("auto", { default_harness: "cursor-agent" })).toBe(
      "cursor-agent"
    )
  })
})
