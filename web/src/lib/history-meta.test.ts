import { describe, expect, it } from "vitest"

import { historyMeta } from "./history-meta"

describe("historyMeta", () => {
  it("shows Built-in checker instead of demo", () => {
    expect(
      historyMeta({
        kind: "run",
        skill: "pdf",
        harness: "demo",
      }).config
    ).toBe("Built-in checker")
  })
})
