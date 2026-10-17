import { describe, expect, it } from "vitest"

import { agentRunName, runButtonLabel } from "./run-summary"

describe("run summary", () => {
  it("names Claude Code on the run button", () => {
    expect(agentRunName("claude")).toBe("Claude Code")
    expect(agentRunName("auto", "claude")).toBe("Claude Code")
    expect(agentRunName("cursor-agent")).toBe("Cursor")
    expect(agentRunName("codex")).toBe("Codex")
    expect(runButtonLabel(4, "Claude Code")).toBe("Run 4 cases on Claude Code")
    expect(runButtonLabel(1, "Cursor")).toBe("Run 1 case on Cursor")
    expect(runButtonLabel(4, "Claude Code", { done: 0, total: 4 })).toBe("0/4 done")
  })
})
