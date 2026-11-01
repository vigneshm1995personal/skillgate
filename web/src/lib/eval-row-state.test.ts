import { describe, expect, it } from "vitest"

import {
  failedHudCount,
  mergeEvalSnapshot,
  queuedTasksFromChecks,
  seededRunningReport,
  suiteStampReady,
  suiteResultKind,
  taskChip,
  taskState,
} from "./eval-row-state"
import { pathEfficiencySoftRow } from "./metrics-label"
import type { Check, RunRecord, TaskResult } from "./types"

const dataset: Check[] = [
  { id: "extract-text-dump", prompt: "Extract the receipt text." },
  { id: "extract-image-stub", prompt: "Read the JPEG, write JSON." },
  { prompt: "Nameless check" },
]

describe("queuedTasksFromChecks", () => {
  it("seeds one queued row per Dataset check and does not invent extras", () => {
    const rows = queuedTasksFromChecks(dataset)
    expect(rows).toHaveLength(3)
    expect(rows.map((row) => row.status)).toEqual([
      "queued",
      "queued",
      "queued",
    ])
    expect(rows.map((row) => row.passed)).toEqual([null, null, null])
    expect(rows[0].id).toBe("extract-text-dump")
    expect(rows[2].id).toBe("check-3")
    expect(rows.every((row) => taskChip(row) === "queued")).toBe(true)
  })
})

describe("failedHudCount", () => {
  it("is 0 while seeded rows are queued and the run is not done", () => {
    const seed = seededRunningReport(dataset, "receipt-photo")
    expect(seed.failed_task_ids).toEqual([])
    expect(seed.tasks.every((task) => taskChip(task) === "queued")).toBe(true)
    expect(failedHudCount({ status: "running" }, seed)).toBe(0)
  })

  it("treats a missing failed_task_ids as 0 while status is not done", () => {
    const report = {
      skill: "receipt-photo",
      passed: null,
      passed_count: 0,
      task_count: 3,
      completed_count: 0,
      tasks: queuedTasksFromChecks(dataset),
    }
    expect(failedHudCount({ status: "running" }, report)).toBe(0)
    expect(failedHudCount({ status: "error" }, report)).toBe(0)
    expect(
      failedHudCount(
        { status: "running" },
        { ...report, failed_task_ids: ["extract-image-stub"] }
      )
    ).toBe(1)
  })
})

describe("taskChip / taskState", () => {
  it("keeps a running row pending even if a stale passed flag is present", () => {
    const task: TaskResult = {
      id: "extract-text-dump",
      status: "running",
      passed: true,
    }
    expect(taskState(task)).toBe("running")
    expect(taskChip(task)).toBe("running")
  })

  it("flips Pass/Fail only when status is done", () => {
    expect(taskChip({ id: "a", status: "done", passed: true })).toBe("pass")
    expect(taskChip({ id: "b", status: "done", passed: false })).toBe("fail")
    expect(taskChip({ id: "c", status: "queued", passed: false })).toBe(
      "queued"
    )
    expect(taskChip({ id: "d", status: "done", passed: null })).toBe("queued")
  })

  it("marks a passed unsure task as review, not fail", () => {
    expect(
      taskChip({ id: "c6", status: "unsure", passed: true, review: true })
    ).toBe("review")
    expect(
      taskChip({ id: "c6", status: "done", passed: true, review: true })
    ).toBe("review")
    expect(taskChip({ id: "wrong", status: "done", passed: false })).toBe(
      "fail"
    )
  })

  it("treats historical rows without status as done only when passed is a boolean", () => {
    expect(taskState({ id: "old", passed: true })).toBe("done")
    expect(taskChip({ id: "old", passed: true })).toBe("pass")
    expect(taskState({ id: "empty" })).toBe("queued")
    expect(taskChip({ id: "empty" })).toBe("queued")
  })
})

describe("mergeEvalSnapshot", () => {
  const seed: RunRecord = {
    status: "running",
    passed: null,
    gate: null,
    completed_count: 0,
    task_count: 3,
    report: seededRunningReport(dataset, "receipt-photo"),
  }

  it("keeps seeded Dataset rows when the first poll has no tasks yet", () => {
    const merged = mergeEvalSnapshot(seed, {
      id: "run-1",
      status: "running",
      passed: null,
      report: null,
    })
    expect(merged.report?.tasks).toHaveLength(3)
    expect(
      merged.report?.tasks?.every((task) => task.status === "queued")
    ).toBe(true)
    expect(merged.id).toBe("run-1")
    expect(failedHudCount(merged, merged.report)).toBe(0)
  })

  it("keeps seeded rows when a hosted poll sends report.tasks = [] (not null)", () => {
    const merged = mergeEvalSnapshot(seed, {
      id: "run-1",
      status: "running",
      passed: null,
      completed_count: 0,
      report: {
        skill: "receipt-photo",
        passed: null,
        passed_count: 0,
        task_count: 0,
        completed_count: 0,
        tasks: [],
      },
    })
    expect(merged.report?.tasks).toHaveLength(3)
    expect(merged.report?.tasks?.map(taskChip)).toEqual([
      "queued",
      "queued",
      "queued",
    ])
    expect(merged.report?.task_count).toBe(3)
    expect(failedHudCount(merged, merged.report)).toBe(0)
  })

  it("applies a finished blob all at once — no stagger", () => {
    const blob: RunRecord = {
      id: "run-1",
      status: "running",
      passed: null,
      completed_count: 2,
      task_count: 3,
      report: {
        skill: "receipt-photo",
        passed: null,
        passed_count: 1,
        task_count: 3,
        completed_count: 2,
        tasks: [
          { id: "extract-text-dump", status: "done", passed: true },
          { id: "extract-image-stub", status: "done", passed: false },
          { id: "check-3", status: "queued", passed: null },
        ],
      },
    }
    const merged = mergeEvalSnapshot(seed, blob)
    expect(merged.report?.tasks?.map(taskChip)).toEqual([
      "pass",
      "fail",
      "queued",
    ])
  })

  it("lets a terminal snapshot replace the seed (stamp may arrive with the last rows)", () => {
    const done: RunRecord = {
      id: "run-1",
      status: "done",
      passed: true,
      gate: "green",
      report: {
        skill: "receipt-photo",
        passed: true,
        passed_count: 3,
        task_count: 3,
        tasks: dataset.map((check, index) => ({
          id: check.id || `check-${index + 1}`,
          status: "done" as const,
          passed: true,
        })),
      },
    }
    const merged = mergeEvalSnapshot(seed, done)
    expect(merged.status).toBe("done")
    expect(
      merged.report?.tasks?.every((task) => taskChip(task) === "pass")
    ).toBe(true)
  })
})

describe("suiteStampReady", () => {
  it("holds stamp and suite metrics until the run is actually done", () => {
    expect(suiteStampReady({ status: "running" })).toBe(false)
    expect(suiteStampReady({ status: "error" })).toBe(true)
    expect(suiteStampReady(null)).toBe(false)
    expect(suiteStampReady({ status: "done" })).toBe(true)
  })
})

describe("suiteResultKind", () => {
  it("is checking while the run is in progress", () => {
    expect(suiteResultKind({ status: "running" }, null, true)).toBe("checking")
    expect(suiteResultKind({ status: "running" }, true, false)).toBe("checking")
  })

  it("is pass when the suite is done and checks passed", () => {
    expect(suiteResultKind({ status: "done" }, true, false)).toBe("pass")
  })

  it("is review when the suite finished needs review", () => {
    expect(
      suiteResultKind({ status: "done", gate: "needs review" }, true, false)
    ).toBe("review")
  })

  it("is fail when the suite is done and checks did not pass", () => {
    expect(suiteResultKind({ status: "done" }, false, false)).toBe("fail")
    expect(suiteResultKind({ status: "done" }, null, false)).toBe("fail")
  })

  it("is error on a worker error", () => {
    expect(suiteResultKind({ status: "error" }, null, false)).toBe("error")
  })

  it("is fail when an error run still has checks", () => {
    expect(suiteResultKind({ status: "error" }, false, false, true)).toBe("fail")
  })

  it("does not treat a finished blob as checking", () => {
    expect(suiteResultKind({ status: "done" }, true, false)).not.toBe(
      "checking"
    )
  })
})

describe("Checks Path chip (#148)", () => {
  it("stays the Jev ordinal, not a raw step count", () => {
    const row = pathEfficiencySoftRow({ choice: "Efficient" }, undefined, {
      path: { steps: 6, had_path: true },
    })
    expect(row.chip).toBe("Direct")
    expect(row.chip).not.toMatch(/step/i)
    expect(pathEfficiencySoftRow({ choice: "Looping" }, undefined).chip).toBe(
      "Looping"
    )
    expect(
      pathEfficiencySoftRow(undefined, undefined, {
        path: { steps: 3, had_path: true },
      }).chip
    ).toBe("—")
  })
})
