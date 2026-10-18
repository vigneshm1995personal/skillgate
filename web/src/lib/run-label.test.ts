import { describe, expect, it } from "vitest"

import { runButtonLabel } from "@/lib/run-label"

describe("runButtonLabel", () => {
  it("names the case count and the agent", () => {
    expect(
      runButtonLabel({
        running: false,
        completed: 0,
        total: 4,
        agent: "claude",
      })
    ).toBe("Run 4 cases on Code agent")
    expect(
      runButtonLabel({
        running: false,
        completed: 0,
        total: 1,
        agent: "cursor-agent",
      })
    ).toBe("Run 1 case on Editor agent")
  })

  it("counts finished cases while a run is in progress", () => {
    expect(
      runButtonLabel({
        running: true,
        completed: 2,
        total: 4,
        agent: "codex",
      })
    ).toBe("2 of 4 done on Terminal agent")
  })

  it("omits the agent when none is picked", () => {
    expect(
      runButtonLabel({ running: false, completed: 0, total: 0, agent: "auto" })
    ).toBe("Run")
    expect(
      runButtonLabel({ running: false, completed: 0, total: 3, agent: "auto" })
    ).toBe("Run 3 cases")
  })
})
