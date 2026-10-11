export type ReasoningEffort = "low" | "medium" | "high" | "ultra"

export type EvalRunConfig = {
  schema?: number
  harness?: string
  harness_pref?: string
  model?: string | null
  timeout_sec?: number | null
  timeout_effective?: number | null
  temperature?: number
  reasoning_effort?: string | null
  source?: string
  applied?: Record<string, boolean>
  fingerprint?: string
  label?: string
}

export type ConfigDiffEntry = {
  field: string
  from?: unknown
  to?: unknown
}

export type EvalConfigDraft = {
  model: string
  timeoutSec: string
  temperature: string
  reasoningEffort: ReasoningEffort
}

export const DEFAULT_EVAL_CONFIG_DRAFT: EvalConfigDraft = {
  model: "",
  timeoutSec: "",
  temperature: "0",
  reasoningEffort: "medium",
}

/** Live cursor-agent / Codex default when the timeout field is left blank. Env still wins if set. */
export const DEFAULT_LIVE_TIMEOUT_SEC = 300

export const MODEL_DEFAULT_VALUE = "__default__"
export const MODEL_CUSTOM_VALUE = "__custom__"

export type ModelOption = { value: string; label: string }

export type SupportedModelsMetaEntry = {
  source?: "live" | "fallback" | "empty"
  error?: "no_key" | "list_failed" | null
}

export type SupportedModelsMeta = Record<string, SupportedModelsMetaEntry>

export function resolveModelHarness(
  pref: string,
  resolvedHarness?: string
): string {
  if (
    pref === "cursor-agent" ||
    pref === "codex" ||
    pref === "llm" ||
    pref === "claude"
  ) {
    return pref
  }
  if (
    resolvedHarness === "codex" ||
    resolvedHarness === "cursor-agent" ||
    resolvedHarness === "llm" ||
    resolvedHarness === "claude"
  ) {
    return resolvedHarness
  }
  return "auto"
}

export function knownModelsForHarness(
  pref: string,
  resolvedHarness?: string,
  catalog?: Record<string, string[]> | null
): string[] {
  const harness = resolveModelHarness(pref, resolvedHarness)
  if (harness === "auto") {
    return []
  }
  return [...(catalog?.[harness] ?? [])]
}

export function modelsForHarness(
  pref: string,
  resolvedHarness?: string,
  catalog?: Record<string, string[]> | null
): ModelOption[] {
  const harness = resolveModelHarness(pref, resolvedHarness)
  const defaultLabel =
    harness === "codex" ? "CLI default (no -m)" : "Agent default"
  const known = knownModelsForHarness(pref, resolvedHarness, catalog).map(
    (id) => ({ value: id, label: id })
  )
  return [
    { value: MODEL_DEFAULT_VALUE, label: defaultLabel },
    ...known,
    { value: MODEL_CUSTOM_VALUE, label: "Custom…" },
  ]
}

export function modelSelectValue(
  model: string,
  options: ModelOption[]
): string {
  const trimmed = model.trim()
  if (!trimmed) {
    return MODEL_DEFAULT_VALUE
  }
  const known = options.some(
    (option) =>
      option.value === trimmed &&
      option.value !== MODEL_DEFAULT_VALUE &&
      option.value !== MODEL_CUSTOM_VALUE
  )
  return known ? trimmed : MODEL_CUSTOM_VALUE
}

export function harnessDisplayName(
  pref: string,
  resolvedHarness?: string
): string {
  if (pref === "auto") {
    const labels: Record<string, string> = {
      codex: "Codex",
      claude: "Claude",
      llm: "LLM",
      "cursor-agent": "Cursor",
    }
    const resolved = labels[resolvedHarness || ""]
    if (!resolved) {
      return "Auto"
    }
    return `Auto · ${resolved}`
  }
  if (pref === "cursor-agent") {
    return "Cursor"
  }
  if (pref === "codex") {
    return "Codex"
  }
  if (pref === "claude") {
    return "Claude"
  }
  if (pref === "llm") {
    return "LLM"
  }
  return pref
}

export function emptyCatalogHint(
  pref: string,
  resolvedHarness?: string,
  meta?: SupportedModelsMeta | null
): string | null {
  const harness = resolveModelHarness(pref, resolvedHarness)
  if (harness === "auto") {
    return null
  }
  if (!meta) {
    return null
  }
  const entry = meta[harness]
  const error = entry?.error
  if (error === "list_failed") {
    return "Could not list models for this key. Use Custom… or Agent default."
  }
  // Auto + no keys: Start is already blocked. Do not add a second message.
  if (pref === "auto") {
    return null
  }
  if (error === "no_key" || entry?.source === "empty" || !entry) {
    return "Set this agent's key in Settings to list models. Custom… still works."
  }
  return "No models listed for this key. Use Custom… or Agent default."
}

export function unsupportedModelHint(
  pref: string,
  resolvedHarness: string | undefined,
  known: string[]
): string {
  if (resolveModelHarness(pref, resolvedHarness) === "codex") {
    if (known.length === 0 || known.length > 8) {
      return "Not on this agent's list. Codex + ChatGPT login needs a Codex model — not gateway ids like openai/gpt-4o-mini."
    }
    return `Not on this agent's list. Codex + ChatGPT login needs a Codex model (${known.join(", ")}) — not gateway ids like openai/gpt-4o-mini.`
  }
  if (known.length === 0 || known.length > 8) {
    return "Not on this agent's list. Pick from the list for this agent or leave Agent default."
  }
  return `Not on this agent's list. Pick from the list for this agent (${known.join(", ")}) or leave Agent default.`
}

export function draftConfigSummary(
  pref: string,
  draft: Pick<EvalConfigDraft, "model" | "timeoutSec">,
  resolvedHarness?: string
): string {
  const parts = [harnessDisplayName(pref, resolvedHarness)]
  const modelRaw = draft.model.trim()
  const model =
    modelRaw === MODEL_CUSTOM_VALUE || modelRaw === MODEL_DEFAULT_VALUE
      ? ""
      : modelRaw
  if (model) {
    parts.push(model)
  }
  const timeout = draft.timeoutSec.trim()
  if (timeout) {
    parts.push(`${timeout}s`)
  }
  return parts.join(" · ")
}

function collapseDuplicateTimeout(label: string): string {
  const parts = label.split(/\s*·\s*/).map((part) => part.trim()).filter(Boolean)
  const out: string[] = []
  for (const part of parts) {
    if (out.length && out[out.length - 1] === part && /^\d+s$/.test(part)) {
      continue
    }
    out.push(part)
  }
  return out.join(" · ")
}

const LIVE_HARNESS_NAMES = new Set(["llm", "cursor-agent", "codex", "claude"])

export function stampRunConfig(
  runConfig?: EvalRunConfig | null,
  reportConfig?: EvalRunConfig | null
): EvalRunConfig | null {
  const live = (cfg?: EvalRunConfig | null) =>
    LIVE_HARNESS_NAMES.has((cfg?.harness || "").toLowerCase())
  if (live(reportConfig)) {
    return reportConfig ?? null
  }
  if (live(runConfig)) {
    return runConfig ?? null
  }
  return reportConfig || runConfig || null
}

export const OLDER_RUN_LABEL = "Older run (before live-only checks)"

export function isLegacyRunCopy(
  text?: string | null,
  harness?: string | null
): boolean {
  const h = (harness || "").toLowerCase()
  if (h === "skip" || h === "demo") {
    return true
  }
  const lower = (text || "").toLowerCase()
  return lower.includes("checker") || lower.includes("live model")
}

function isStaleAutoLabel(label: string, harness?: string): boolean {
  if (!LIVE_HARNESS_NAMES.has((harness || "").toLowerCase())) {
    return false
  }
  return /^auto(\s*·|\s*$)/i.test(label.trim())
}

export function configLabel(config?: EvalRunConfig | null): string {
  if (!config) {
    return ""
  }
  if (isLegacyRunCopy(config.label, config.harness)) {
    return OLDER_RUN_LABEL
  }
  if (config.label && !isStaleAutoLabel(config.label, config.harness)) {
    return collapseDuplicateTimeout(
      config.label
        .replace(/\bcursor-agent\b/g, "Cursor")
        .replace(/\bcodex\b/g, "Codex")
        .replace(/\bclaude\b/g, "Claude")
    )
  }
  const resolved = (config.harness || config.harness_pref || "auto").trim()
  const parts: string[] = [harnessDisplayName(resolved, config.harness)]
  if (config.model) {
    if (config.applied?.via_gateway) {
      parts.push(`${config.model} via gateway`)
    } else {
      parts.push(config.model)
    }
  }
  const timeout = config.timeout_effective ?? config.timeout_sec
  if (timeout) {
    parts.push(`${timeout}s`)
  }
  if (config.harness === "codex") {
    parts.push(config.reasoning_effort || "medium")
  } else if (config.temperature && config.applied?.temperature) {
    parts.push(`temp ${config.temperature}`)
  }
  return collapseDuplicateTimeout(parts.join(" · "))
}

const CONFIG_FIELD_LABEL: Record<string, string> = {
  timeout_sec: "Time limit",
  timeout_effective: "Time limit",
  harness: "Agent",
  harness_pref: "Agent",
  model: "Model",
  temperature: "Temperature",
  reasoning_effort: "Reasoning",
}

function plainTimeout(value: unknown): string | null {
  const n = typeof value === "number" ? value : Number(value)
  if (!Number.isFinite(n) || n <= 0) {
    return null
  }
  if (n % 60 === 0) {
    const minutes = n / 60
    return minutes === 1 ? "1 minute" : `${minutes} minutes`
  }
  return n === 1 ? "1 second" : `${n} seconds`
}

function plainConfigValue(field: string, value: unknown): string {
  if (value == null || value === "" || value === "—") {
    return "not set"
  }
  if (field === "timeout_sec" || field === "timeout_effective") {
    return plainTimeout(value) || String(value)
  }
  if (field === "harness" || field === "harness_pref") {
    return harnessDisplayName(String(value), String(value))
  }
  return String(value)
}

/** Customer sentence for a config diff row. */
export function plainConfigDiff(entries: ConfigDiffEntry[]): string {
  return entries
    .map((entry) => {
      const field = entry.field || "setting"
      const label = CONFIG_FIELD_LABEL[field] || field.replace(/_/g, " ")
      const from = plainConfigValue(field, entry.from)
      const to = plainConfigValue(field, entry.to)
      if (from === "not set") {
        return `${label} is now ${to}.`
      }
      if (to === "not set") {
        return `${label} is no longer ${from}.`
      }
      return `${label} changed from ${from} to ${to}.`
    })
    .filter(Boolean)
    .join(" ")
}

export function draftToApiConfig(
  draft: EvalConfigDraft,
  includeReasoning: boolean
): {
  model: string | null
  timeout_sec: number | null
  temperature: number
  reasoning_effort: ReasoningEffort | null
} {
  const timeoutRaw = draft.timeoutSec.trim()
  const timeoutParsed = timeoutRaw === "" ? Number.NaN : Number(timeoutRaw)
  const tempRaw = draft.temperature.trim()
  const tempParsed = tempRaw === "" ? 0 : Number(tempRaw)
  const modelRaw = draft.model.trim()
  const model =
    modelRaw === MODEL_CUSTOM_VALUE || modelRaw === MODEL_DEFAULT_VALUE
      ? ""
      : modelRaw
  return {
    model: model || null,
    timeout_sec: Number.isFinite(timeoutParsed) ? timeoutParsed : null,
    temperature: Number.isFinite(tempParsed) ? tempParsed : 0,
    reasoning_effort: includeReasoning ? draft.reasoningEffort : null,
  }
}
