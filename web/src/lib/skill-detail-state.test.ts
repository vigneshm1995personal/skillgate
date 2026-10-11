import { describe, expect, it } from "vitest"

import { skillDetailStatus } from "./skill-detail-state"

describe("skillDetailStatus", () => {
  it("stays loading until the skill request settles", () => {
    expect(skillDetailStatus({ skillSettled: false, error: "" })).toBe("loading")
  })

  it("leaves loading on success, including an empty skill", () => {
    expect(skillDetailStatus({ skillSettled: true, error: "" })).toBe("ready")
  })

  it("leaves loading on error", () => {
    expect(
      skillDetailStatus({ skillSettled: true, error: "Could not load this skill." })
    ).toBe("error")
  })
})
