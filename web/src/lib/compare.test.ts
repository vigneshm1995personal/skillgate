import { describe, expect, it } from "vitest"

import { armChecksLine, disagreementCount, passLabel } from "@/lib/compare"

describe("compare helpers", () => {
  it("counts disagreements", () => {
    expect(
      disagreementCount([
        { case_id: "a", disagreement: true },
        { case_id: "b", disagreement: false },
      ])
    ).toBe(1)
  })

  it("labels pass fail", () => {
    expect(passLabel(true)).toBe("Pass")
    expect(passLabel(false)).toBe("Fail")
    expect(passLabel(null)).toBe("—")
  })

  it("formats arm checks line", () => {
    expect(armChecksLine({ arm_id: "a", passed_count: 6, task_count: 8 })).toBe(
      "6/8 Pass"
    )
  })
})
