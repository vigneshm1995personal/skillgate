import { describe, expect, it } from "vitest"

import type { RunRecord } from "@/lib/types"
import {
  TRYOUT_LABEL,
  deployAllowedForLiveGate,
  emptySkillRunSlot,
  isTryoutRun,
  liveGateRun,
  pinBelongsToSkill,
  runForCheck,
  shownGateRun,
  skillSlotKey,
} from "./skill-run-state"

const greenGate: RunRecord = {
  id: "full-green",
  status: "done",
  skill: "pdf",
  harness: "cursor-agent",
  gate_decision: "cleared",
  report: { skill: "pdf", passed_count: 2, task_count: 2, tasks: [] },
}

const redGate: RunRecord = {
  id: "full-red",
  status: "done",
  skill: "pdf",
  harness: "cursor-agent",
  gate_decision: "blocked",
  report: { skill: "pdf", passed_count: 0, task_count: 2, tasks: [] },
}

const tryoutFail: RunRecord = {
  id: "try-1",
  status: "done",
  skill: "pdf",
  tryout: true,
  harness: "cursor-agent",
  gate_decision: "pending",
  report: {
    skill: "pdf",
    tryout: true,
    passed_count: 0,
    task_count: 1,
    tasks: [{ id: "extract-text", prompt: "Extract", passed: false, status: "done" }],
  },
}

const otherSkillPin: RunRecord = {
  id: "csv-pin",
  status: "done",
  skill: "csv-clean",
  harness: "cursor-agent",
  gate_decision: "cleared",
  report: { skill: "csv-clean", passed_count: 1, task_count: 1, tasks: [] },
}

describe("isTryoutRun", () => {
  it("reads the top-level or report flag", () => {
    expect(isTryoutRun(greenGate)).toBe(false)
    expect(isTryoutRun(tryoutFail)).toBe(true)
    expect(isTryoutRun({ status: "done", report: { tryout: true, skill: "pdf", passed_count: 0, task_count: 1, tasks: [] } })).toBe(true)
  })
})

describe("shownGateRun / liveGateRun", () => {
  it("never shows a try-out as the Gate stamp", () => {
    const slot = { ...emptySkillRunSlot(), gate: greenGate, tryout: tryoutFail }
    expect(shownGateRun(slot, "pdf")?.id).toBe("full-green")
    expect(liveGateRun(slot, "pdf")?.id).toBe("full-green")
  })

  it("ignores a pin from another skill", () => {
    const slot = { ...emptySkillRunSlot(), gate: redGate, pin: otherSkillPin }
    expect(pinBelongsToSkill(slot.pin, "pdf")).toBe(false)
    expect(shownGateRun(slot, "pdf")?.id).toBe("full-red")
  })

  it("uses a pin only when it belongs to the selected skill", () => {
    const slot = { ...emptySkillRunSlot(), gate: redGate, pin: greenGate }
    expect(shownGateRun(slot, "pdf")?.id).toBe("full-green")
    expect(liveGateRun(slot, "pdf")?.id).toBe("full-red")
  })
})

describe("deployAllowedForLiveGate", () => {
  it("follows the live full run, not a try-out or a stale history gate", () => {
    expect(
      deployAllowedForLiveGate({
        skill: { name: "pdf" },
        liveGate: greenGate,
        gateRunning: false,
      })
    ).toBe(true)
    expect(
      deployAllowedForLiveGate({
        skill: { name: "pdf" },
        liveGate: tryoutFail,
        gateRunning: false,
      })
    ).toBe(false)
    expect(
      deployAllowedForLiveGate({
        skill: { name: "pdf" },
        liveGate: greenGate,
        gateRunning: true,
      })
    ).toBe(false)
    expect(
      deployAllowedForLiveGate({
        skill: { name: "pdf" },
        liveGate: redGate,
        gateRunning: false,
      })
    ).toBe(false)
  })

  it("unlocks a green built-in checker run in local mode", () => {
    const demoGreen: RunRecord = {
      id: "demo-green",
      status: "done",
      skill: "pdf",
      harness: "demo",
      gate_decision: "cleared",
      report: { skill: "pdf", passed_count: 2, task_count: 2, tasks: [], harness: "demo" },
    }
    expect(
      deployAllowedForLiveGate({
        skill: { name: "pdf" },
        liveGate: demoGreen,
        gateRunning: false,
        mode: "local",
      })
    ).toBe(true)
    expect(
      deployAllowedForLiveGate({
        skill: { name: "pdf" },
        liveGate: demoGreen,
        gateRunning: false,
        mode: "cloud",
      })
    ).toBe(false)
  })
})

describe("runForCheck", () => {
  it("overlays only the matching try-out check", () => {
    const matched = runForCheck(
      { id: "extract-text", prompt: "Extract" },
      greenGate,
      tryoutFail
    )
    expect(matched?.id).toBe("try-1")
    const other = runForCheck(
      { id: "other", prompt: "Something else" },
      greenGate,
      tryoutFail
    )
    expect(other?.id).toBe("full-green")
  })
})

describe("skillSlotKey", () => {
  it("keys slots by skill name", () => {
    expect(skillSlotKey({ name: "pdf" })).toBe("pdf")
    expect(skillSlotKey("csv-clean")).toBe("csv-clean")
    expect(TRYOUT_LABEL).toContain("doesn't change Deploy")
  })
})
