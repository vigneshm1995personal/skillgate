import type { Check, Report, RunRecord, TaskResult } from "@/lib/types"

/** Dataset checks as queued Gate rows — pending until that task actually finishes. */
export function queuedTasksFromChecks(checks: Check[]): TaskResult[] {
  return checks.map((check, index) => ({
    id: (check.id || "").trim() || `check-${index + 1}`,
    prompt: check.prompt,
    status: "queued" as const,
    passed: null,
  }))
}

export function seededRunningReport(
  checks: Check[],
  skillName?: string | null
): Report {
  const tasks = queuedTasksFromChecks(checks)
  return {
    skill: skillName || "",
    passed: null,
    passed_count: 0,
    task_count: tasks.length,
    completed_count: 0,
    current_task_id: null,
    failed_task_ids: [],
    tasks,
  }
}

/**
 * Evaluating HUD Failed count. A missing `failed_task_ids` must not be read as
 * task_count − passed while the run is still open (that paints every queued
 * check as Failed).
 */
export function failedHudCount(
  record: Pick<RunRecord, "status"> | null | undefined,
  report:
    | Pick<Report, "failed_task_ids" | "task_count" | "passed_count">
    | null
    | undefined
): number {
  const ids = report?.failed_task_ids
  if (Array.isArray(ids)) {
    return ids.length
  }
  if (record?.status !== "done") {
    return 0
  }
  const passed = report?.passed_count ?? 0
  return Math.max(0, (report?.task_count ?? 0) - passed)
}

export function taskState(task: TaskResult): "queued" | "running" | "done" {
  if (task.status === "queued" || task.status === "running") {
    return task.status
  }
  if (
    task.status === "done" ||
    task.status === "unsure" ||
    task.status === "pass" ||
    task.status === "fail"
  ) {
    return "done"
  }
  if (typeof task.passed === "boolean" || task.review === true) {
    return "done"
  }
  return "queued"
}

/** Pass/Fail only after the task is actually done. Running/queued never inherit a prior verdict. */
export function taskChip(
  task: TaskResult
): "queued" | "running" | "pass" | "fail" | "skipped" | "review" {
  const state = taskState(task)
  if (state === "running") {
    return "running"
  }
  if (task.skipped) {
    return "skipped"
  }
  if (
    state === "done" &&
    (task.review === true || task.status === "unsure") &&
    task.passed !== false
  ) {
    return "review"
  }
  if (state === "done" && task.passed === true) {
    return "pass"
  }
  if (state === "done" && task.passed === false) {
    return "fail"
  }
  return "queued"
}

export type SuiteResultKind = "idle" | "checking" | "pass" | "fail" | "error" | "review"

/** GREEN/RED stamp + suite tokens/path/cost — only after the run has actually finished. */
export function suiteStampReady(
  record: Pick<RunRecord, "status"> | null | undefined
): boolean {
  return record?.status === "done" || record?.status === "error"
}

/** Suite result shell. Checking until the run is actually done; Pass if checks passed. */
export function suiteResultKind(
  record: Pick<RunRecord, "status" | "gate" | "report"> | null | undefined,
  reportPassed: boolean | null | undefined,
  evaluating: boolean,
  hasTasks = false
): SuiteResultKind {
  if (evaluating || record?.status === "running") {
    return "checking"
  }
  if (record?.status === "error") {
    return hasTasks ? "fail" : "error"
  }
  if (record?.status === "done") {
    const gate = record.gate || record.report?.gate
    if (gate === "needs review") {
      return "review"
    }
    return reportPassed === true ? "pass" : "fail"
  }
  return "idle"
}

export function runBelongsToSkill(
  record: Pick<RunRecord, "skill" | "report"> | null | undefined,
  skillName?: string | null
): boolean {
  const name = (skillName || "").trim()
  if (!name || !record) {
    return !record || !name
  }
  const runSkill = (record.report?.skill || record.skill || "").trim()
  if (!runSkill) {
    return true
  }
  return runSkill === name
}

/**
 * Keep seeded Dataset rows until the worker publishes a real task list.
 * Do not stagger: if the snapshot already has N done rows, all N land at once.
 */
export function mergeEvalSnapshot(
  previous: RunRecord | null | undefined,
  incoming: RunRecord
): RunRecord {
  if (incoming.status !== "running") {
    return incoming
  }
  const incomingTasks = incoming.report?.tasks ?? []
  if (incomingTasks.length > 0) {
    return incoming
  }
  if (previous?.status !== "running") {
    return incoming
  }
  const previousTasks = previous.report?.tasks ?? []
  if (!previousTasks.length) {
    return incoming
  }
  if (!incoming.report) {
    return {
      ...incoming,
      report: previous.report,
      task_count:
        incoming.task_count ?? previous.task_count ?? previousTasks.length,
    }
  }
  return {
    ...incoming,
    report: {
      ...incoming.report,
      tasks: previousTasks,
      task_count: incoming.report.task_count || previousTasks.length,
    },
  }
}
