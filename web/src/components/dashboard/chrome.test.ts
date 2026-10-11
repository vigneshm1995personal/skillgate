import { describe, expect, it } from "vitest"

import { gateTone, stampBadgeProps } from "@/components/dashboard/chrome"

describe("stampBadgeProps", () => {
  it("shows a passing run as Ready, not Blocked", () => {
    const props = stampBadgeProps("pass")
    expect(props.passed).toBe(true)
    expect(gateTone(props.gate, props.passed)).toBe("green")
    expect(gateTone("blocked", false)).toBe("red")
  })
})
