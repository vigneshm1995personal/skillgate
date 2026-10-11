import {
  LEFTOVER_PREFIX_MIN,
  assistantMessage,
  collapseAssistantSpans,
  leftoverOfCompleted,
  sameTurnText,
} from "@/lib/collapse-assistant-spans"
import type { OtlpSpan } from "@/lib/types"

export type TimelineStepStatus = "pass" | "fail" | "neutral"

export type TimelineStep = {
  id: string
  title: string
  subtitle?: string
  status: TimelineStepStatus
  detail?: string
  commands: string[]
}

type Segment = {
  narration: string[]
  command?: string
}

function customerVisibleText(text: string): string {
  return text
    .replace(/Gate pre-selected skill \(skip catalog discovery\)\s*/gi, "")
    .replace(/\bSKILLGATE_TASK(?:=[^\s]*)?/g, "the task")
    .replace(/\bevals\/(?:goldens|fixtures)\/([^\s]+)/g, "$1")
}

function polishStep(step: TimelineStep): TimelineStep {
  return {
    ...step,
    title: customerVisibleText(step.title),
    subtitle: step.subtitle ? customerVisibleText(step.subtitle) : step.subtitle,
    detail: step.detail ? customerVisibleText(step.detail) : step.detail,
    commands: step.commands.map((item) => customerVisibleText(item)),
  }
}

function basename(path: string): string {
  const cleaned = path.replace(/\\/g, "/").replace(/['"]/g, "")
  const parts = cleaned.split("/").filter(Boolean)
  return parts[parts.length - 1] ?? cleaned
}

const SKILL_STOPWORDS = new Set([
  "the",
  "a",
  "an",
  "this",
  "that",
  "skill",
  "skills",
  "only",
  "first",
  "now",
])

function skillFromPath(text: string): string | undefined {
  const patterns = [
    /\.skillgate\/skills\/([^/\s]+)/,
    /skills\/([^/\s]+)\/SKILL\.md/,
    /`([a-z0-9][a-z0-9._-]*)`\s+skill/i,
    /select(?:ing|ed)?\s+(?:the\s+)?`([a-z0-9][a-z0-9._-]*)`/i,
    /exact match:\s*`([a-z0-9][a-z0-9._-]*)`/i,
  ]
  for (const pattern of patterns) {
    const m = text.match(pattern)
    const name = m?.[1]
    if (name && !SKILL_STOPWORDS.has(name.toLowerCase())) {
      return name
    }
  }
  return undefined
}

function fileFromCommand(command: string): string | undefined {
  const m =
    command.match(
      /(?:changed|edit|write|read|cat|sed[^\n]*\s)\s+([^\s]+\.\w+)/i
    ) ||
    command.match(/([^\s]+\/[^\s]+\.\w{1,8})/) ||
    command.match(/([A-Za-z0-9._-]+\.(?:md|json|txt|pdf|py|ya?ml))/)
  return m?.[1] ? basename(m[1]) : undefined
}

function classify(
  narration: string,
  command: string | undefined
): Pick<TimelineStep, "title" | "subtitle"> {
  const blob = `${narration}\n${command ?? ""}`.toLowerCase()
  const file = command ? fileFromCommand(command) : undefined
  const skill = skillFromPath(`${narration}\n${command ?? ""}`)

  // Only real selection acts — not closing summaries like "Selected the pdf skill and…"
  const selectedLine = narration.match(/^\s*selected:\s*(\S+)/im)?.[1]
  const selectHit =
    blob.includes("selected.json") ||
    blob.includes("catalog.md") ||
    blob.includes("pre-selected") ||
    blob.includes("skip catalog") ||
    Boolean(selectedLine) ||
    /\bskill selection\b/.test(blob) ||
    (/\$\s*(?:edit|write|changed)\b/.test(blob) && blob.includes("selected.json"))
  if (selectHit) {
    const picked =
      selectedLine && selectedLine.toLowerCase() !== "none"
        ? selectedLine
        : skill
    return {
      title: "Select skill",
      subtitle: picked,
    }
  }
  if (blob.includes("skill.md") || /read .*\.md/.test(blob)) {
    if (blob.includes("skill.md") || blob.includes("/skills/")) {
      return {
        title: "Read the skill instructions",
        subtitle: skill,
      }
    }
  }
  if (
    /\bverif/.test(blob) ||
    blob.includes("confirm") ||
    (command?.includes("sed -n") && file === "standup.md")
  ) {
    return {
      title: "Verify",
      subtitle: file,
    }
  }
  if (
    /\b(changed|edit|writing|created|write)\b/.test(blob) ||
    command?.startsWith("edit ") ||
    command?.startsWith("changed ")
  ) {
    const out = file && file !== "selected.json" ? file : file
    if (out === "selected.json") {
      return { title: "Select skill", subtitle: skill }
    }
    return {
      title: out ? `Write ${out}` : "Write artifact",
      subtitle: out && out !== skill ? undefined : skill,
    }
  }
  if (
    blob.includes("agent_entry") ||
    blob.includes("/scripts/") ||
    /\.py(?:\s|$)/.test(blob)
  ) {
    return { title: "Ran the skill's script", subtitle: skill }
  }
  if (
    /\b(extract|shell|python|run|glob|mkdir)\b/.test(blob) ||
    command?.startsWith("shell ") ||
    command?.startsWith("glob ")
  ) {
    return {
      title: file ? shellTitle(file, command) : "Run tool",
      subtitle: command ? truncateAtWord(command, 80) : undefined,
    }
  }
  if (command) {
    return {
      title: file ? `Touch ${file}` : "Agent step",
      subtitle: truncateAtWord(command, 96),
    }
  }
  const first = truncateAtWord(narration.trim().split(/\n/)[0] || "", 72)
  return { title: first || "Step", subtitle: undefined }
}

function segmentTranscript(transcript: string): Segment[] {
  const lines = transcript
    .replace(/\r\n/g, "\n")
    .split("\n")
    .filter((line) => !isHarnessNote(line))
  const segments: Segment[] = []
  let narration: string[] = []

  const flush = (command?: string) => {
    if (!command && narration.length === 0) return
    segments.push({ narration: [...narration], command })
    narration = []
  }

  for (const raw of lines) {
    const trimmed = raw.trim()
    if (trimmed.startsWith("$ ")) {
      flush(trimmed.slice(2).trim())
      continue
    }
    if (trimmed.toUpperCase().startsWith("RUN:")) {
      flush(trimmed.slice(4).trim())
      continue
    }
    if (/^ran\s+\S+/.test(trimmed) && /exit=\d+/.test(trimmed)) {
      flush(trimmed.replace(/^ran\s+/i, "").replace(/\s+exit=\d+\s*$/i, "").trim())
      continue
    }
    // "changed /path" style from some harnesses
    if (/^changed\s+\S+/.test(trimmed)) {
      flush(trimmed)
      continue
    }
    narration.push(raw)
  }
  if (narration.length) flush()
  return segments
}

function mergeSameTitle(steps: TimelineStep[]): TimelineStep[] {
  const out: TimelineStep[] = []
  for (const step of steps) {
    const prev = out[out.length - 1]
    if (prev && prev.title === step.title && prev.subtitle === step.subtitle) {
      prev.commands.push(...step.commands)
      if (step.detail) {
        prev.detail = [prev.detail, step.detail].filter(Boolean).join("\n\n")
      }
      continue
    }
    out.push(step)
  }
  return out
}


function dedupeSelectSkill(steps: TimelineStep[]): TimelineStep[] {
  const out: TimelineStep[] = []
  let sawSelect = false
  for (const step of steps) {
    if (step.title === "Select skill") {
      if (sawSelect) {
        // Later false positives (e.g. "select the …") — drop.
        continue
      }
      sawSelect = true
    }
    out.push(step)
  }
  return out
}

/**
 * Turn a harness transcript into timeline steps (harness-neutral).
 *
 * Structured agent streams (Cursor stream-json, Codex exec JSONL, Claude
 * stream-json) are parsed line by line, skipping non-JSON preamble such as
 * `vercel-sandbox:` progress notes or dependency-install output. Plain-text
 * transcripts (`$ cmd` style) fall back to the narration heuristic.
 */
export function parseTranscriptSteps(
  transcript: string | null | undefined,
  opts?: { passed?: boolean | null }
): TimelineStep[] {
  const text = (transcript ?? "").trim()
  if (!text) return []
  if (transcriptHasAgentJson(text)) {
    // Never run the prose heuristic over raw JSON — it invents steps from the
    // prompt echo. Zero steps here just means the agent has not acted yet.
    return spansToTimelineSteps(jsonlToSpans(text), opts)
  }
  return parseNarrationSteps(text, opts)
}

function parseNarrationSteps(
  text: string,
  opts?: { passed?: boolean | null }
): TimelineStep[] {

  const segments = segmentTranscript(text)
  const status: TimelineStepStatus =
    opts?.passed === false ? "neutral" : opts?.passed === true ? "pass" : "neutral"

  const steps: TimelineStep[] = segments.map((seg, index) => {
    const narration = seg.narration.join("\n").trim()
    const { title, subtitle } = classify(narration, seg.command)
    const detailParts = [
      narration || undefined,
      seg.command ? `$ ${seg.command}` : undefined,
    ].filter(Boolean)
    return {
      id: `step-${index}`,
      title,
      subtitle,
      status,
      detail: detailParts.join("\n\n") || undefined,
      commands: seg.command ? [seg.command] : [],
    }
  })

  const meaningful = steps.filter((step) => {
    if (step.commands.length > 0) return true
    // Keep narration-only when it names a real phase; drop "Created …" closers.
    const title = step.title.toLowerCase()
    if (title.startsWith("created ")) return false
    if (title === "write artifact" && !step.detail?.includes("$")) return false
    if (title === "step") return false
    return Boolean(step.detail && step.detail.length > 40)
  })
  const merged = dedupeSelectSkill(mergeSameTitle(meaningful))
  if (opts?.passed === true) {
    for (const step of merged) step.status = "pass"
  }
  return merged.map(polishStep)
}

export function countHarnessCommands(transcript: string | null | undefined): number {
  const text = (transcript ?? "").trim()
  if (!text) return 0
  if (transcriptHasAgentJson(text)) {
    return jsonlToSpans(text).filter((span) => span.name.startsWith("tool.") || span.name === "skill.select").length
  }
  return text.split("\n").filter((line) => {
    const t = line.trim()
    return (
      t.startsWith("$ ") ||
      t.toUpperCase().startsWith("RUN:") ||
      (/^ran\s+\S+/.test(t) && /exit=\d+/.test(t)) ||
      /^changed\s+\S+/.test(t)
    )
  }).length
}


function spanAttrs(span: OtlpSpan): Record<string, string> {
  const out: Record<string, string> = {}
  for (const item of span.attributes ?? []) {
    const key = item.key
    const value = item.value
    if (!key || !value) continue
    if (value.stringValue != null) out[key] = value.stringValue
    else if (value.intValue != null) out[key] = String(value.intValue)
    else if (value.doubleValue != null) out[key] = String(value.doubleValue)
    else if (value.boolValue != null) out[key] = String(value.boolValue)
  }
  return out
}

function isSkillScript(value?: string): boolean {
  if (!value) return false
  const blob = value.replace(/\\/g, "/").toLowerCase()
  return (
    blob.includes("/scripts/") ||
    blob.includes("agent_entry.py") ||
    blob.includes(".skillgate/") ||
    /(^|\/)[a-z0-9._-]+\.py(?:\s|$)/i.test(blob)
  )
}

function titleForSpan(span: OtlpSpan): { title: string; subtitle?: string; detail?: string } {
  const attrs = spanAttrs(span)
  const file = attrs["file.name"] || attrs["file.path"]
  const tool = attrs["gen_ai.tool.name"]
  const args = attrs["gen_ai.tool.call.arguments"]
  const name = span.name || ""
  if (name === "eval.check") {
    return { title: "Check", subtitle: undefined }
  }
  if (name === "skill.select") {
    return { title: "Select skill", subtitle: file?.replace(/selected\.json$/, "") || file }
  }
  if (name === "tool.read" && (file?.includes("SKILL.md") || attrs["file.path"]?.includes("SKILL.md"))) {
    return { title: "Read the skill instructions", subtitle: undefined, detail: args }
  }
  if (name === "tool.read") {
    const base = file ? file.split("/").pop() : undefined
    return { title: base ? `Read ${base}` : "Read file", subtitle: undefined, detail: args }
  }
  if (name === "tool.write") {
    const base = file ? file.split("/").pop() : undefined
    return { title: base ? `Write ${base}` : "Write artifact", subtitle: undefined, detail: args }
  }
  if (name === "tool.shell") {
    const raw = file || args || ""
    const script = isSkillScript(raw) || isSkillScript(args)
    return {
      title: script ? "Ran the skill's script" : shellTitle(raw, args),
      subtitle: undefined,
      detail: args,
    }
  }
  if (name === "tool.search") {
    return { title: "Search", subtitle: args ? truncateAtWord(args, 96) : undefined, detail: args }
  }
  if (name.startsWith("tool.")) {
    return {
      title: `Used ${tool || name.slice(5)}`,
      subtitle: args ? truncateAtWord(args, 96) : undefined,
      detail: args,
    }
  }
  if (name === "gen_ai.error") {
    const msg = attrs["error.message"]
    return {
      title: "Agent error",
      subtitle: msg ? truncateAtWord(msg, 96) : undefined,
      detail: msg,
    }
  }
  if (name === "gen_ai.assistant") {
    const msg = attrs["gen_ai.assistant.message"]
    return {
      title: "Assistant",
      subtitle: msg ? truncateAtWord(previewPlainText(msg), 72) : undefined,
      detail: msg,
    }
  }
  return { title: name, subtitle: tool || file, detail: args }
}

/** Prefer OTLP spans when the harness emitted them; skip the root eval.check. */
export function spansToTimelineSteps(
  spans: OtlpSpan[] | null | undefined,
  opts?: { passed?: boolean | null }
): TimelineStep[] {
  const list = (spans ?? []).filter((span) => span.name && span.name !== "eval.check")
  if (!list.length) return []
  const statusBase: TimelineStepStatus =
    opts?.passed === true ? "pass" : opts?.passed === false ? "neutral" : "neutral"
  const steps: TimelineStep[] = list.map((span, index) => {
    const { title, subtitle, detail } = titleForSpan(span)
    const code = span.status?.code
    const status: TimelineStepStatus =
      span.name === "gen_ai.error" || code === 2
        ? "fail"
        : statusBase === "pass"
          ? "pass"
          : "neutral"
    const args = spanAttrs(span)["gen_ai.tool.call.arguments"]
    return {
      id: span.spanId ?? `span-${index}`,
      title,
      subtitle,
      status,
      detail,
      commands: args ? [args] : [],
    }
  })
  const merged = dedupeSelectSkill(mergeSameTitle(steps))
  if (opts?.passed === true) {
    for (const step of merged) step.status = "pass"
  }
  return merged.map(polishStep)
}


// ---------------------------------------------------------------------------
// Structured agent streams (Cursor / Codex / Claude) → OTLP-shaped spans.
// Mirrors skillgate_ai.spans.spans_from_jsonl so live tails without server
// spans still render the same steps.
// ---------------------------------------------------------------------------

type Json = Record<string, unknown>

const HARNESS_NOTE = /^\s*(?:vercel-sandbox|skillgate|sandbox):\s/i

export function isHarnessNote(line: string): boolean {
  return HARNESS_NOTE.test(line)
}

function parseJsonLine(line: string): Json | null {
  const text = line.trim()
  if (!text.startsWith("{")) return null
  try {
    const value: unknown = JSON.parse(text)
    return value && typeof value === "object" && !Array.isArray(value)
      ? (value as Json)
      : null
  } catch {
    return null
  }
}

function asObj(value: unknown): Json | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Json)
    : null
}

function asStr(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}

export function transcriptHasAgentJson(transcript: string | null | undefined): boolean {
  for (const line of (transcript ?? "").split("\n")) {
    const obj = parseJsonLine(line)
    if (obj && typeof obj.type === "string") return true
  }
  return false
}

function mkSpan(
  name: string,
  index: number,
  attrs: Record<string, string>,
  error = false
): OtlpSpan {
  return {
    name,
    spanId: `jsonl-${index}`,
    status: error ? { code: 2 } : undefined,
    attributes: Object.entries(attrs)
      .filter(([, v]) => v)
      .map(([key, v]) => ({ key, value: { stringValue: v } })),
  }
}

function toolSpanName(tool: string, path: string): string {
  const t = tool.toLowerCase()
  if (path.endsWith("selected.json") && /write|edit|apply|replace/.test(t)) return "skill.select"
  if (["shell", "bash", "run", "command_execution"].includes(t)) return "tool.shell"
  if (["read", "readfile", "read_file"].includes(t)) return "tool.read"
  if (["write", "edit", "multiedit", "searchreplace", "applypatch", "str_replace"].includes(t))
    return "tool.write"
  if (["glob", "grep", "rg", "search", "ls"].includes(t)) return "tool.search"
  return `tool.${t}`
}

function toolAttrs(tool: string, args: Json | null): { attrs: Record<string, string>; path: string } {
  let summary = ""
  let path = ""
  for (const key of ["command", "path", "file_path", "globPattern", "pattern", "query"]) {
    const value = asStr(args?.[key])
    if (value) {
      summary = value
      if (key === "path" || key === "file_path") path = value
      break
    }
  }
  return {
    path,
    attrs: {
      "gen_ai.tool.name": tool.toLowerCase(),
      "gen_ai.tool.call.arguments": summary.slice(0, 500),
      "file.path": path,
      "file.name": path ? basename(path) : "",
    },
  }
}

const ASSISTANT_MSG_MAX = 100_000

function assistantTextFromEvent(obj: Record<string, unknown>): string {
  const content = asObj(obj.message)?.content
  const bits: string[] = []
  for (const part of Array.isArray(content) ? content : []) {
    const p = asObj(part)
    // Do not trim: Cursor deltas include leading/trailing spaces when a space
    // belongs in the message. Trimming would glue "selected"+" it" into
    // "selectedit" after the write-time space-insert bug is gone.
    if (p?.type === "text" && typeof p.text === "string" && p.text) bits.push(p.text)
  }
  return bits.join("")
}


export function glueAssistantDelta(prev: string, delta: string): string {
  if (!prev) return delta
  if (!delta) return prev
  return prev + delta
}

/** One-line preview: drop markdown markers, then cut on a word boundary. */
export function previewPlainText(text: string): string {
  return text.replace(/`+/g, "").replace(/\*+/g, "").replace(/\s+/g, " ").trim()
}

/** Truncate on a word boundary and add an ellipsis. Never cut mid-word. */
export function truncateAtWord(text: string, max = 72): string {
  const t = text.replace(/\s+/g, " ").trim()
  if (t.length <= max) {
    return t
  }
  const slice = t.slice(0, max)
  const next = t[max] ?? ""
  if (!next || /\s/.test(next) || /\s/.test(slice[slice.length - 1] ?? "")) {
    return `${slice.trimEnd()}…`
  }
  const bound = slice.replace(/\s+\S*$/, "").trimEnd()
  if (bound.length >= Math.min(40, Math.floor(max * 0.55))) {
    return `${bound}…`
  }
  return `${slice.trimEnd()}…`
}

function shellTitle(raw: string, args?: string): string {
  const blob = `${raw} ${args || ""}`
  const pdf = blob.match(/([A-Za-z0-9._-]+\.pdf)/i)
  if (/pdfreader|pypdf|pdfplumber|pymupdf/i.test(blob) && pdf) {
    return `Read ${pdf[1]}`
  }
  const py = blob.match(/([A-Za-z0-9._-]+\.py)/i)
  if (py && !isSkillScript(blob)) {
    return `Ran ${py[1]}`
  }
  const base = raw.replace(/\\/g, "/").split("/").pop()
  if (base && base.includes(".")) {
    const clean = base.replace(/['")]+$/, "").replace(/^['"(]+/, "")
    if (clean && !clean.includes("(")) {
      return `Ran ${clean}`
    }
  }
  if (pdf) {
    return `Read ${pdf[1]}`
  }
  return "Run tool"
}

function setSpanAttr(span: OtlpSpan, key: string, value: string): void {
  const attrs = span.attributes ?? (span.attributes = [])
  const existing = attrs.find((a) => a.key === key)
  if (existing) {
    existing.value = { stringValue: value }
    return
  }
  attrs.push({ key, value: { stringValue: value } })
}

function cursorAssistantCompleted(obj: Json): boolean {
  if (obj.model_call_id) return true
  return !("timestamp_ms" in obj)
}

function lastAssistantIdx(spans: OtlpSpan[]): number | null {
  for (let i = spans.length - 1; i >= 0; i -= 1) {
    if (spans[i]?.name === "gen_ai.assistant") return i
  }
  return null
}

/**
 * Parse Cursor stream-json, Codex exec JSONL and Claude stream-json lines.
 *
 * Token deltas are for live streaming only. A completed assistant event
 * (`model_call_id`, or a flush without `timestamp_ms`) replaces the buffer.
 * Leftover deltas after that are ignored. Never concatenate two copies.
 */
export function jsonlToSpans(transcript: string | null | undefined): OtlpSpan[] {
  const spans: OtlpSpan[] = []
  let index = 0
  let openAssistantIdx: number | null = null
  let assistantSealed = false
  const completedTexts: string[] = []

  const writeAssistant = (idx: number, text: string) => {
    setSpanAttr(spans[idx], "gen_ai.assistant.message", text.slice(0, ASSISTANT_MSG_MAX))
  }

  const noteCompleted = (text: string) => {
    const stripped = text.trim()
    if (stripped && !completedTexts.includes(stripped)) completedTexts.push(stripped)
  }

  const deltaLeftoverOfCompleted = (delta: string) =>
    completedTexts.some((text) => leftoverOfCompleted(delta, text))

  const sameTurnIndices = (full: string): number[] => {
    const matches: number[] = []
    let crossedTool = false
    for (let idx = spans.length - 1; idx >= 0; idx -= 1) {
      const span = spans[idx]
      if (span?.name === "gen_ai.assistant") {
        const msg = assistantMessage(span)
        if (!sameTurnText(msg, full)) break
        if (crossedTool && full.startsWith(msg) && msg.length >= LEFTOVER_PREFIX_MIN) break
        matches.push(idx)
        continue
      }
      crossedTool = true
    }
    matches.reverse()
    return matches
  }

  const applyCompleted = (fullRaw: string) => {
    const full = fullRaw.slice(0, ASSISTANT_MSG_MAX)
    const matches = sameTurnIndices(full)
    if (matches.length) {
      const keep = matches[0]
      const current = assistantMessage(spans[keep])
      if (assistantSealed && keep === openAssistantIdx && full.length <= current.length) {
        return
      }
      writeAssistant(keep, full)
      for (let i = matches.length - 1; i >= 1; i -= 1) {
        spans.splice(matches[i], 1)
      }
      openAssistantIdx = keep
      assistantSealed = true
      noteCompleted(full)
      return
    }
    index += 1
    spans.push(
      mkSpan("gen_ai.assistant", index, {
        "gen_ai.assistant.message": full,
      })
    )
    openAssistantIdx = spans.length - 1
    assistantSealed = true
    noteCompleted(full)
  }

  const applyPartial = (delta: string) => {
    if (deltaLeftoverOfCompleted(delta)) {
      return
    }
    if (assistantSealed && openAssistantIdx !== null) {
      const current = assistantMessage(spans[openAssistantIdx])
      if (leftoverOfCompleted(delta, current)) {
        return
      }
      openAssistantIdx = null
      assistantSealed = false
    }
    if (openAssistantIdx === null) {
      const prevIdx = lastAssistantIdx(spans)
      if (prevIdx !== null && leftoverOfCompleted(delta, assistantMessage(spans[prevIdx]))) {
        return
      }
      index += 1
      spans.push(
        mkSpan("gen_ai.assistant", index, {
          "gen_ai.assistant.message": delta.slice(0, ASSISTANT_MSG_MAX),
        })
      )
      openAssistantIdx = spans.length - 1
      assistantSealed = false
      return
    }
    const prevMsg = assistantMessage(spans[openAssistantIdx])
    writeAssistant(openAssistantIdx, glueAssistantDelta(prevMsg, delta).slice(0, ASSISTANT_MSG_MAX))
  }

  const closeAssistantTurn = () => {
    openAssistantIdx = null
    assistantSealed = false
  }

  for (const line of (transcript ?? "").split("\n")) {
    const obj = parseJsonLine(line)
    if (!obj) continue
    index += 1
    const kind = asStr(obj.type)
    if (kind === "tool_call") {
      if (obj.subtype === "completed") continue
      closeAssistantTurn()
      const call = asObj(obj.tool_call)
      for (const [key, payload] of Object.entries(call ?? {})) {
        if (!key.endsWith("ToolCall")) continue
        const tool = key.slice(0, -"ToolCall".length)
        const { attrs, path } = toolAttrs(tool, asObj(asObj(payload)?.args))
        spans.push(mkSpan(toolSpanName(tool, path), index, attrs))
        break
      }
    } else if (kind === "item.completed") {
      closeAssistantTurn()
      const item = asObj(obj.item)
      const itype = asStr(item?.type)
      if (itype === "command_execution") {
        spans.push(
          mkSpan("tool.shell", index, {
            "gen_ai.tool.name": "shell",
            "gen_ai.tool.call.arguments": asStr(item?.command).slice(0, 500),
          })
        )
      } else if (itype === "file_change") {
        const changes = Array.isArray(item?.changes) ? item.changes : []
        const path = asStr(asObj(changes[0])?.path)
        const name =
          path.endsWith("selected.json") || path.includes("catalog.md") ? "skill.select" : "tool.write"
        spans.push(
          mkSpan(name, index, {
            "gen_ai.tool.name": "write",
            "file.path": path,
            "file.name": path ? basename(path) : "",
          })
        )
      } else if (itype === "agent_message") {
        const text = asStr(item?.text)
        if (text) {
          noteCompleted(text)
          spans.push(
            mkSpan("gen_ai.assistant", index, {
              "gen_ai.assistant.message": text.slice(0, ASSISTANT_MSG_MAX),
            })
          )
        }
      }
    } else if (kind === "assistant") {
      const joined = assistantTextFromEvent(obj)
      if (joined) {
        if (cursorAssistantCompleted(obj)) applyCompleted(joined)
        else applyPartial(joined)
      }
      const content = asObj(obj.message)?.content
      for (const part of Array.isArray(content) ? content : []) {
        const p = asObj(part)
        if (!p || p.type !== "tool_use") continue
        closeAssistantTurn()
        const tool = asStr(p.name) || "tool"
        const { attrs, path } = toolAttrs(tool, asObj(p.input))
        spans.push(mkSpan(toolSpanName(tool, path), index, attrs))
      }
    } else if (kind === "error" || kind === "turn.failed") {
      closeAssistantTurn()
      const err = obj.error
      const msg = kind === "error" ? asStr(obj.message) : asStr(asObj(err)?.message) || asStr(err)
      if (msg) spans.push(mkSpan("gen_ai.error", index, { "error.message": msg.slice(0, 400) }, true))
    }
  }
  return collapseAssistantSpans(spans, completedTexts)
}

/** JSONL completed-text rebuild when the transcript has agent events. */
export function pickTimelineSteps(opts: {
  transcript?: string | null
  spans?: OtlpSpan[] | null
  passed?: boolean | null
}): TimelineStep[] {
  if (transcriptHasAgentJson(opts.transcript)) {
    const fromJsonl = parseTranscriptSteps(opts.transcript, { passed: opts.passed })
    if (fromJsonl.length) return fromJsonl
  }
  if (opts.spans?.length) {
    const fromSpans = spansToTimelineSteps(collapseAssistantSpans(opts.spans), {
      passed: opts.passed,
    })
    if (fromSpans.length) return fromSpans
  }
  return parseTranscriptSteps(opts.transcript, { passed: opts.passed })
}

// ---------------------------------------------------------------------------
// Pre-agent phase (sandbox boot / deps install) for the running empty state.
// ---------------------------------------------------------------------------

/** True when an assistant/tool event exists (not just system/init/user). */
export function transcriptHasAgentAction(transcript: string | null | undefined): boolean {
  for (const line of (transcript ?? "").split("\n")) {
    const obj = parseJsonLine(line)
    if (!obj || typeof obj.type !== "string") continue
    const kind = obj.type
    if (kind === "assistant" || kind === "tool_call" || kind === "item.completed") return true
    if (kind === "tool_use" || kind === "content_block_start") return true
  }
  return false
}

export function harnessPhaseLabel(transcript: string | null | undefined): string {
  const lines = (transcript ?? "").split("\n")
  // Steps take over once an assistant/tool event exists; until then prefer a
  // precise pre-step label (system/init alone used to look like a hang).
  if (transcriptHasAgentAction(transcript)) return "Waiting for the agent's first step…"
  if (transcriptHasAgentJson(transcript)) return "Agent connected — starting first action…"
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    const line = lines[i].trim().toLowerCase()
    if (!line) continue
    if (/running .*agent|running codex|running claude|running cursor/.test(line))
      return "Agent connected — starting first action…"
    if (/ensuring .* cli/.test(line)) return "Preparing the agent CLI…"
    if (/skill deps|uv pip install|installing uv|deps snapshot|pip install/.test(line))
      return "Installing skill dependencies…"
    if (/writing \d+ workspace files/.test(line)) return "Copying check files into the sandbox…"
    if (/creating microvm|sandbox/.test(line)) return "Preparing the workspace…"
  }
  return "Preparing the workspace…"
}

const PHASE_ORDER = [
  "Preparing the workspace…",
  "Copying check files into the sandbox…",
  "Installing skill dependencies…",
  "Preparing the agent CLI…",
  "Agent connected — starting first action…",
  "Waiting for the agent's first step…",
]

/** Rank of a pre-agent phase label (higher = later). Unknown labels rank 0. */
export function harnessPhaseRank(label: string): number {
  const index = PHASE_ORDER.indexOf(label)
  return index < 0 ? 0 : index
}
