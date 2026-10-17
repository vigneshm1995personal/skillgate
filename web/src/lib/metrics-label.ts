import type {
  JudgeAnswer,
  JudgeQuestion,
  TaskMetrics,
  TaskResult,
  Usage,
  VsBaseline,
} from "@/lib/types"

function trimZero(value: number) {
  return String(Number(value.toFixed(1))).replace(/\.0$/, "")
}

export function formatTokens(value?: number | null) {
  if (value == null || Number.isNaN(value)) {
    return null
  }
  if (value < 1000) {
    return String(value)
  }
  if (value < 1_000_000) {
    return `${trimZero(value / 1000)}k`
  }
  return `${trimZero(value / 1_000_000)}M`
}

export function formatCost(value?: number | null) {
  if (value == null) {
    return null
  }
  if (value > 0 && value < 0.01) {
    return "<$0.01"
  }
  return `$${value.toFixed(2)}`
}

/** Total cost with optional scoring breakdown when the judge reported dollars. */
export function formatCostWithScoring(usage?: Usage | null) {
  if (usage?.agent_cost_label) {
    const scoring = formatCost(usage.judge_cost_usd)
    return scoring
      ? `${usage.agent_cost_label} (${scoring} scoring)`
      : usage.agent_cost_label
  }
  const total = formatCost(usage?.cost_usd)
  const scoring = formatCost(usage?.judge_cost_usd)
  if (total && scoring) {
    return `${total} (${scoring} scoring)`
  }
  return total
}

type PathBits = {
  steps?: number
  had_path?: boolean
}

function suitePath(
  metrics?: { path?: PathBits } | null,
  tasks?: Array<{ metrics?: TaskMetrics | null }> | null
): PathBits {
  const direct = metrics?.path
  if (direct && (typeof direct.steps === "number" || direct.had_path != null)) {
    return direct
  }
  let steps = 0
  let had = false
  let saw = false
  for (const task of tasks ?? []) {
    const path = task.metrics?.path
    if (!path) {
      continue
    }
    saw = true
    if (typeof path.steps === "number") {
      steps += path.steps
    }
    if (path.had_path || (typeof path.steps === "number" && path.steps > 0)) {
      had = true
    }
  }
  return saw ? { steps, had_path: had } : {}
}

export type MetricDisplay = {
  value: string
  hint: string
  recorded: boolean
}

const NOT_RECORDED = "not recorded"

function pathRecorded(path: PathBits): boolean {
  if (path.had_path && typeof path.steps === "number") {
    return true
  }
  return typeof path.steps === "number" && path.steps > 0
}

/** Suite Tokens cell. Never invents a total from in/out. */
export function tokenMetricDisplay(usage?: Usage | null): MetricDisplay {
  const total = formatTokens(usage?.tokens_total)
  if (!total) {
    return { value: "—", hint: NOT_RECORDED, recorded: false }
  }
  const parts = [
    formatTokens(usage?.tokens_in)
      ? `${formatTokens(usage?.tokens_in)} in`
      : null,
    formatTokens(usage?.tokens_out)
      ? `${formatTokens(usage?.tokens_out)} out`
      : null,
  ].filter(Boolean)
  return { value: total, hint: parts.join(" · "), recorded: true }
}

/** Suite Path cell (steps). */
export function pathMetricDisplay(
  metrics?: { path?: PathBits } | null,
  tasks?: Array<{ metrics?: TaskMetrics | null }> | null
): MetricDisplay {
  const path = suitePath(metrics, tasks)
  if (!pathRecorded(path) || typeof path.steps !== "number") {
    return { value: "—", hint: NOT_RECORDED, recorded: false }
  }
  return {
    value: String(path.steps),
    hint: path.steps === 1 ? "step" : "steps",
    recorded: true,
  }
}

/** Suite Cost cell. Uses harness cost_usd only — Never invents dollars from tokens. */
export function costMetricDisplay(usage?: Usage | null): MetricDisplay {
  const cost = formatCostWithScoring(usage)
  if (usage?.agent_cost_label) {
    return { value: cost || usage.agent_cost_label, hint: "", recorded: true }
  }
  if (cost) {
    return { value: cost, hint: "", recorded: true }
  }
  if (usage?.tokens_total != null || usage?.cost_unknown) {
    return { value: "Unknown", hint: "Cost not reported by the agent run", recorded: false }
  }
  if (!cost) {
    return { value: "—", hint: NOT_RECORDED, recorded: false }
  }
  return { value: cost, hint: "", recorded: true }
}

/** Tokens · steps · cost when recorded. Omits numbers this run did not record. */
export function runMetricsLine(opts: {
  usage?: Usage | null
  metrics?: { path?: PathBits } | null
  tasks?: Array<{ metrics?: TaskMetrics | null }> | null
}): string {
  const parts: string[] = []
  const tokens = formatTokens(opts.usage?.tokens_total)
  if (tokens) {
    parts.push(`${tokens} tok`)
  }
  const path = suitePath(opts.metrics, opts.tasks)
  if (pathRecorded(path) && typeof path.steps === "number") {
    parts.push(`${path.steps} steps`)
  }
  const cost = formatCostWithScoring(opts.usage)
  if (cost) {
    parts.push(cost)
  }
  return parts.join(" · ")
}

export function taskMetricsLine(
  usage?: Usage | null,
  metrics?: TaskMetrics | null
) {
  return runMetricsLine({
    usage,
    metrics,
    tasks: metrics ? [{ metrics }] : [],
  })
}

/** Empty usage matches the check row: Not checked, never Tokens — · — steps. */
export function checkUsageLine(
  usage?: Usage | null,
  metrics?: TaskMetrics | null
) {
  return taskMetricsLine(usage, metrics) || "Not checked"
}

export function compactTaskMetrics(
  task: Pick<TaskResult, "usage" | "metrics">
) {
  const tokens = formatTokens(task.usage?.tokens_total)
  const steps = task.metrics?.path?.steps
  const had = task.metrics?.path?.had_path
  const parts: string[] = []
  if (tokens) {
    parts.push(`${tokens} tok`)
  }
  if (had || (typeof steps === "number" && steps > 0)) {
    parts.push(`${steps ?? 0} steps`)
  }
  const cost = formatCostWithScoring(task.usage)
  if (cost) {
    parts.push(cost)
  }
  return parts.length ? parts.join(" · ") : null
}

/** Soft Checks-card rows. Tone is never `"bad"` (red stays Pass-lock fails). */
export type SoftCheckTone = "ok" | "soft" | "na"

export type SoftCheckRowModel = {
  chip: string
  tone: SoftCheckTone
  reason: string
  extra?: string[]
}

const REASON_TOKEN_OVER = "This case went over its token budget."
const REASON_PATH_OVER = "This case took more steps than its path budget."
const REASON_BOTH_OVER = "This case went over its token and path budgets."
const REASON_TOKEN_CLOSED =
  "This case has a token budget, but the run did not report tokens."
const REASON_PATH_CLOSED =
  "This case has a step budget, but the run did not record a path."

function firstReason(
  reasons: string[] | undefined,
  candidates: string[]
): string | undefined {
  return reasons?.find((item) => candidates.includes(item))
}

/** Budget-over / fail-closed — must match skillgate_ai.metrics.evaluate_task_metrics */
function pathBudgetOver(metrics?: TaskMetrics | null): boolean {
  const max = metrics?.budgets?.max_steps
  if (max == null) {
    return false
  }
  const path = metrics?.path ?? {}
  if (!pathRecorded(path)) {
    return true
  }
  return typeof path.steps === "number" && path.steps > max
}

/** Budget-over / fail-closed — must match skillgate_ai.metrics.evaluate_task_metrics */
function tokenBudgetOver(
  usage?: Usage | null,
  metrics?: TaskMetrics | null
): boolean {
  const budget = metrics?.budgets?.tokens_total
  if (budget == null) {
    return false
  }
  const total = usage?.tokens_total
  if (typeof total !== "number" || Number.isNaN(total)) {
    return true
  }
  return total > budget
}

function signedDelta(value: number, unit: string): string {
  const sign = value >= 0 ? "+" : "−"
  return `${sign}${Math.abs(value)} ${unit} vs baseline`
}

const PATH_EFFICIENCY_TONES: Record<string, { chip: string; tone: SoftCheckTone }> = {
  efficient: { chip: "Direct", tone: "ok" },
  acceptable: { chip: "Acceptable", tone: "ok" },
  looping: { chip: "Looping", tone: "soft" },
  wasteful: { chip: "Wasteful", tone: "soft" },
}

const PATH_EFFICIENCY_CRITERIA: Record<string, string> = {
  Direct:
    "The skill took a direct path: no repeated tool calls, no loops, no wasted steps.",
  Efficient:
    "The skill took a direct path: no repeated tool calls, no loops, no wasted steps.",
  Acceptable: "The skill finished with only minor extra steps and no looping.",
  Looping:
    "The skill repeated the same or near-same tool calls without making progress.",
  Wasteful: "The skill spent many tool calls off-task or thrashing.",
}

function pathCriteria(
  criteria: JudgeQuestion["criteria"] | undefined,
  chip: string
): string | undefined {
  if (!criteria || Array.isArray(criteria)) {
    return PATH_EFFICIENCY_CRITERIA[chip]
  }
  const exact = criteria[chip]
  if (typeof exact === "string" && exact.trim()) {
    return exact.trim()
  }
  const key = chip.toLowerCase()
  for (const [criterionKey, value] of Object.entries(criteria)) {
    if (
      criterionKey.toLowerCase() === key &&
      typeof value === "string" &&
      value.trim()
    ) {
      return value.trim()
    }
  }
  return PATH_EFFICIENCY_CRITERIA[chip]
}

function pathMechanicalExtras(
  metrics?: TaskMetrics | null,
  vsBaseline?: VsBaseline | null
): string[] {
  const path: NonNullable<TaskMetrics["path"]> = metrics?.path ?? {}
  const recorded = pathRecorded(path) && typeof path.steps === "number"
  const over = pathBudgetOver(metrics)
  const max = metrics?.budgets?.max_steps
  const extra: string[] = []

  if (!recorded) {
    if (over) {
      extra.push(
        firstReason(metrics?.reasons, [
          REASON_BOTH_OVER,
          REASON_PATH_CLOSED,
          REASON_PATH_OVER,
        ]) ?? REASON_PATH_CLOSED
      )
    }
    if (typeof vsBaseline?.delta_steps === "number") {
      const abs = Math.abs(vsBaseline.delta_steps)
      extra.push(signedDelta(vsBaseline.delta_steps, abs === 1 ? "step" : "steps"))
    }
    return extra
  }

  extra.push(
    "Path steps count skill.select and tool.* spans, not assistant turns."
  )
  const n = path.steps as number
  extra.push(
    typeof path.errors === "number" && path.errors > 0
      ? `${n} steps · ${path.errors} errors`
      : `${n} steps`
  )
  if (max != null) {
    if (over) {
      extra.push(
        firstReason(metrics?.reasons, [
          REASON_BOTH_OVER,
          REASON_PATH_OVER,
          REASON_PATH_CLOSED,
        ]) ?? REASON_PATH_OVER
      )
    } else {
      extra.push(`Budget ${n} / ${max} steps.`)
    }
  }
  if (typeof vsBaseline?.delta_steps === "number") {
    const abs = Math.abs(vsBaseline.delta_steps)
    extra.push(signedDelta(vsBaseline.delta_steps, abs === 1 ? "step" : "steps"))
  }
  return extra
}

/** Opened-row Path line. Null means omit the row. */
export function pathOpenedCaption(
  softChoice?: string | null,
  metrics?: TaskMetrics | null
): string | null {
  const choice = typeof softChoice === "string" ? softChoice.trim() : ""
  if (choice) {
    return PATH_EFFICIENCY_TONES[choice.toLowerCase()]?.chip || choice
  }
  const path = metrics?.path
  if (!path) {
    return null
  }
  const steps = path.steps
  if (typeof steps === "number" && steps > 0) {
    return null
  }
  if (path.had_path) {
    return "This check did not record any steps."
  }
  return null
}

/** Checks Path chip is the Jev ordinal — never `{n} steps`. Tone is never `"bad"`. */
export function pathEfficiencySoftRow(
  answer?: JudgeAnswer | null,
  question?: JudgeQuestion | null,
  metrics?: TaskMetrics | null,
  vsBaseline?: VsBaseline | null
): SoftCheckRowModel {
  const extra = pathMechanicalExtras(metrics, vsBaseline)
  const raw = typeof answer?.choice === "string" ? answer.choice.trim() : ""
  const mapped = raw ? PATH_EFFICIENCY_TONES[raw.toLowerCase()] : undefined
  if (!mapped) {
    return {
      chip: "—",
      tone: "na",
      reason: "This run has no path efficiency check.",
      extra: extra.length ? extra : undefined,
    }
  }
  const fromAnswer =
    typeof answer?.reason === "string" && answer.reason.trim()
      ? answer.reason.trim()
      : undefined
  return {
    chip: mapped.chip,
    tone: mapped.tone,
    reason:
      fromAnswer ||
      pathCriteria(question?.criteria, raw) ||
      pathCriteria(question?.criteria, mapped.chip) ||
      mapped.chip,
    extra: extra.length ? extra : undefined,
  }
}

export function tokenSoftRow(
  usage?: Usage | null,
  metrics?: TaskMetrics | null,
  vsBaseline?: VsBaseline | null
): SoftCheckRowModel {
  const total = usage?.tokens_total
  const recorded = typeof total === "number" && !Number.isNaN(total)
  const over = tokenBudgetOver(usage, metrics)
  const budget = metrics?.budgets?.tokens_total
  const extra: string[] = []

  if (!recorded) {
    if (over) {
      extra.push(
        firstReason(metrics?.reasons, [
          REASON_BOTH_OVER,
          REASON_TOKEN_CLOSED,
          REASON_TOKEN_OVER,
        ]) ?? REASON_TOKEN_CLOSED
      )
    }
    if (typeof vsBaseline?.delta_tokens === "number") {
      extra.push(signedDelta(vsBaseline.delta_tokens, "tok"))
    }
    return {
      chip: "—",
      tone: over ? "soft" : "na",
      reason: "This run did not report tokens.",
      extra: extra.length ? extra : undefined,
    }
  }

  const totalLabel = formatTokens(total)
  const budgetLabel = budget == null ? null : formatTokens(budget)
  const chip =
    budget == null || !budgetLabel
      ? `${totalLabel} tok`
      : `${totalLabel} / ${budgetLabel} tok`

  const breakdown = [
    formatTokens(usage?.tokens_in)
      ? `${formatTokens(usage?.tokens_in)} in`
      : null,
    formatTokens(usage?.tokens_out)
      ? `${formatTokens(usage?.tokens_out)} out`
      : null,
    `${totalLabel} total`,
  ].filter(Boolean)
  const cost = formatCost(usage?.cost_usd)
  extra.push(cost ? `${breakdown.join(" · ")} · ${cost}` : breakdown.join(" · "))
  if (budget != null && budgetLabel) {
    if (over) {
      extra.push(
        firstReason(metrics?.reasons, [
          REASON_BOTH_OVER,
          REASON_TOKEN_OVER,
          REASON_TOKEN_CLOSED,
        ]) ?? REASON_TOKEN_OVER
      )
    } else {
      extra.push(`Budget ${totalLabel} / ${budgetLabel} tok.`)
    }
  }
  if (typeof vsBaseline?.delta_tokens === "number") {
    extra.push(signedDelta(vsBaseline.delta_tokens, "tok"))
  }
  return {
    chip,
    tone: over ? "soft" : "ok",
    reason: "Tokens for this check. Never estimated.",
    extra,
  }
}
