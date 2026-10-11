import { DEFAULT_OUTPUT_PATH, type Check, type PromoteDraft, type TaskResult } from "@/lib/types"

const CONTAINS_RE = /(?:does not contain|missing)\s+['"](.+?)['"]/i

export function draftCheckFromFailure(
  task: TaskResult,
  existingChecks: Check[] = [],
  defaultOutputPath = DEFAULT_OUTPUT_PATH
): PromoteDraft {
  if (task.passed !== false) {
    throw new Error("Only a failed Gate task can be promoted to a check.")
  }
  const prompt = (task.prompt ?? "").trim()
  if (!prompt) {
    throw new Error("Failed task is missing a prompt.")
  }
  const existing = matchExistingCheck(task, existingChecks)
  const shouldTrigger =
    "expect_skill" in task
      ? Boolean(task.expect_skill)
      : existing?.should_trigger !== false
  const contains =
    (existing?.contains ?? "").trim() || containsFromTask(task) || ""
  const fallback = (defaultOutputPath || "").trim() || DEFAULT_OUTPUT_PATH
  const outputPath =
    (existing?.output_path ?? "").trim() || (contains ? fallback : "")
  return {
    check: {
      id: regressionId(task.id || "task"),
      prompt,
      should_trigger: shouldTrigger,
      contains,
      output_path: outputPath,
      min_pages: existing?.min_pages ?? null,
      files: existing?.files ? [...existing.files] : [],
      needs_upload: Boolean(existing?.needs_upload) && !(existing?.files?.length),
    },
    hints: hintsFromTask(task),
    source_task_id: task.id,
  }
}

export function regressionId(taskId: string): string {
  const slug = taskId.trim().replace(/[^a-zA-Z0-9_-]+/g, "-") || "task"
  if (slug.toLowerCase().startsWith("regression-")) {
    return slug
  }
  return `regression-${slug}`
}

function matchExistingCheck(
  task: TaskResult,
  checks: Check[]
): Check | undefined {
  const taskId = (task.id || "").trim()
  const prompt = (task.prompt ?? "").trim()
  const candidates = new Set(
    [taskId, taskId.startsWith("regression-") ? taskId.slice("regression-".length) : ""]
      .filter(Boolean)
  )
  const byId = checks.find((check) => check.id && candidates.has(check.id))
  if (byId) {
    return byId
  }
  return checks.find((check) => prompt && check.prompt.trim() === prompt)
}

function containsFromTask(task: TaskResult): string {
  for (const score of task.scores ?? []) {
    if (score.scorer !== "task_completion" && score.scorer !== "rubric") {
      continue
    }
    const expected = (score.expected ?? "").trim()
    if (expected && expected.toLowerCase() !== "none") {
      return expected
    }
  }
  const blobs = [
    ...(task.failures ?? []),
    ...(task.scores ?? []).flatMap((score) => [score.detail ?? "", score.headline ?? ""]),
  ]
  const match = CONTAINS_RE.exec(blobs.join("\n"))
  return match?.[1] ?? ""
}

function hintsFromTask(task: TaskResult): string[] {
  const hints: string[] = []
  const seen = new Set<string>()
  const add = (value?: string | null) => {
    const text = (value ?? "").trim()
    if (!text || seen.has(text)) {
      return
    }
    seen.add(text)
    hints.push(text)
  }
  add(task.advice?.headline)
  add(task.advice?.why)
  for (const failure of task.failures ?? []) {
    add(failure)
  }
  for (const score of task.scores ?? []) {
    if (score.passed === true) {
      continue
    }
    add(score.headline || score.detail)
  }
  return hints.slice(0, 6)
}
