import { isLegacyRunCopy, OLDER_RUN_LABEL } from "@/lib/eval-config"
import { pathOpenedCaption } from "@/lib/metrics-label"
import type { JudgeAnswer, JudgeResult, Report, TaskResult } from "@/lib/types"

export const CHECK_QUESTION_ORDER = [
  "task_completion",
  "correctness",
  "instruction_adherence",
  "evidence_action_validity",
  "result_quality",
] as const

export const CHECK_QUESTION_LABELS: Record<string, string> = {
  task_completion: "Got the job done?",
  correctness: "Got it right?",
  instruction_adherence: "Followed the rules?",
  evidence_action_validity: "Used the right evidence/actions?",
  result_quality: "Delivered a good result?",
}

const PASS_LOCK: Record<string, string[]> = {
  task_completion: ["fully completed"],
  correctness: ["correct"],
  instruction_adherence: ["fully followed"],
  evidence_action_validity: ["fully supported", "n/a"],
  result_quality: ["clear and complete", "mostly good"],
}

export const CONFIDENCE_WARN = 0.5

const CHECKS_DUMP = /^Checks:\s+/i
const GENERIC_FAIL = "This check did not pass."
const CHECKS_PLAIN = /^Checks:\s+(\w+)\s+(.+?)(?:\s+\(need\s+(.+?)\))?(?:\s+[—–-]\s+(.*))?$/i
const SCORER_CODE =
  /^(?:Checks:\s+)?([a-z_]+)\s+([a-z0-9_-]+)(?:\s+\(need\s+([a-z0-9_-]+)\))?$/i
const SKILL_DIDNT_START =
  "The skill didn't start for this request — its description doesn't match what was asked."
const FILE_WARN =
  /did not finish a file this skill is supposed to write|meant to write a file/i
const DRAFT_WARN = /used draft checks, not the saved Dataset/i
const NO_DATASET_WARN = /this skill has no saved Dataset/i
const COVER_WARN = /did not cover the saved Dataset/i

export type OpenedAnswer = {
  id: string
  label: string
  answer: string
}

function trimText(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}

function isChecksDump(text: string): boolean {
  return CHECKS_DUMP.test(text)
}

function isGenericFail(text: string): boolean {
  return text === GENERIC_FAIL
}

function mentionsPdf(hint: string): boolean {
  return /\bpdf\b|\.pdf\b/i.test(hint)
}

function looksLikeTriggerMiss(text: string): boolean {
  const blob = text.toLowerCase()
  return (
    blob.includes("didn't trigger") ||
    blob.includes("did not trigger") ||
    blob.includes("didn’t trigger") ||
    blob.includes("skill didn’t trigger") ||
    blob.includes("skill didn't trigger")
  )
}

/** Map stored scorer codes to a customer sentence. */
export function scorerCodeToPlain(raw: string, hint = ""): string {
  const text = trimText(raw)
  if (!text) {
    return text
  }
  if (looksLikeTriggerMiss(`${text} ${hint}`)) {
    return SKILL_DIDNT_START
  }
  const match = text.match(SCORER_CODE)
  if (match) {
    const cell = trimText(match[1]).toLowerCase()
    const choiceRaw = trimText(match[2])
    const choice = choiceRaw.toLowerCase()
    const need = trimText(match[3]).toLowerCase()
    if (
      cell === "blocker" ||
      cell === "skill_trigger" ||
      choice === "skill_trigger" ||
      choice === "trigger" ||
      (need === "none" && cell === "blocker")
    ) {
      return SKILL_DIDNT_START
    }
    if (cell === "outcome" && (choice === "partial" || choice === "off_target" || choice === "partially")) {
      return mentionsPdf(`${hint} ${text}`)
        ? "The PDF was only partly right."
        : "The result was only partly right."
    }
    if (cell === "outcome") {
      return "The result didn't match what was asked."
    }
    const label = CHECK_QUESTION_LABELS[cell]
    if (label && choiceRaw) {
      return `${label} ${choiceRaw.replace(/_/g, " ")}.`
    }
  }
  if (/\bskill_trigger\b/i.test(text) && /\bnone\b/i.test(text)) {
    return SKILL_DIDNT_START
  }
  if (/\boutcome\b.*\bpartial\b/i.test(text)) {
    return mentionsPdf(hint)
      ? "The PDF was only partly right."
      : "The result was only partly right."
  }
  return text
}

/** Turn a Checks: dump or scorer code into a customer sentence. */
export function plainFailReason(raw: string, hint = ""): string | null {
  const text = trimText(raw)
  if (!text || isGenericFail(text)) {
    return null
  }
  const mapped = scorerCodeToPlain(text, hint)
  if (mapped !== text) {
    return mapped
  }
  if (!isChecksDump(text)) {
    return mapped
  }
  const match = text.match(CHECKS_PLAIN)
  if (!match) {
    const rest = text.replace(CHECKS_DUMP, "").trim()
    return rest ? scorerCodeToPlain(rest, hint) : null
  }
  const afterDash = trimText(match[4])
  if (afterDash) {
    return afterDash
  }
  const key = trimText(match[1]).toLowerCase()
  const label = CHECK_QUESTION_LABELS[key]
  const choice = trimText(match[2]).replace(/\s+\(need\s+.+\)$/i, "")
  if (label && choice) {
    return `${label} ${choice}.`
  }
  const rest = text.replace(CHECKS_DUMP, "").trim()
  return rest ? scorerCodeToPlain(rest, hint) : null
}

export function checkHeadline(task: {
  id?: string | null
  prompt?: string | null
}): string {
  const prompt = trimText(task.prompt).replace(/\s+/g, " ")
  if (prompt) {
    const cut = prompt.match(/^.+?[.?!](?=\s|$)/)
    let one = (cut && cut[0]) || prompt
    if (one.length > 96) {
      one = `${one.slice(0, 93).replace(/\s+\S*$/, "")}…`
    }
    if (!/[.?!…]$/.test(one) && !/\.{3}$/.test(one)) {
      one += "."
    }
    return one
  }
  const words = String(task.id || "")
    .replace(/[-_]+/g, " ")
    .trim()
  if (!words) {
    return "This check should pass."
  }
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}.`
}

export function happenedLine(task: TaskResult): string {
  const hint = `${task.prompt || ""} ${task.id || ""}`
  if (task.skipped) {
    for (const item of task.failures ?? []) {
      const text = plainFailReason(item, hint)
      if (text) {
        return text
      }
    }
    const judgeWhy =
      plainFailReason(trimText(task.judge?.fail_reason), hint) ||
      plainFailReason(trimText(task.judge?.why), hint) ||
      plainFailReason(trimText(task.judge?.reason), hint)
    if (judgeWhy) {
      return judgeWhy
    }
    return "Skipped"
  }
  if (task.passed) {
    const stampedPass = trimText(task.happened)
    if (stampedPass && !isGenericFail(stampedPass) && !isChecksDump(stampedPass)) {
      return scorerCodeToPlain(stampedPass, hint)
    }
    if (task.expect_skill === null && !task.selected_skill) {
      return "No skill was picked, as expected."
    }
    return "Output matched what was expected."
  }
  const stamped = trimText(task.happened)
  if (stamped && !isGenericFail(stamped) && !isChecksDump(stamped)) {
    return scorerCodeToPlain(stamped, hint)
  }
  const failReason =
    plainFailReason(trimText(task.judge?.fail_reason), hint) ||
    plainFailReason(trimText(task.judge?.why), hint)
  if (failReason) {
    return failReason
  }
  for (const item of task.judge?.reasons ?? []) {
    const text = plainFailReason(item, hint)
    if (text) {
      return text
    }
  }
  for (const item of task.failures ?? []) {
    const text = plainFailReason(item, hint)
    if (text) {
      return text
    }
  }
  return GENERIC_FAIL
}

export function extraFailWhy(task: TaskResult): string | null {
  if (task.passed !== false || task.skipped) {
    return null
  }
  const happened = happenedLine(task)
  const hint = `${task.prompt || ""} ${task.id || ""}`
  const why =
    plainFailReason(trimText(task.judge?.fail_reason), hint) ||
    plainFailReason(trimText(task.judge?.why), hint)
  if (!why || why === happened) {
    return null
  }
  return why
}

function isOpenAIJudge(judge: JudgeResult | null | undefined): boolean {
  const provider = trimText(judge?.provider).toLowerCase()
  const backend = trimText(judge?.backend).toLowerCase()
  const model = trimText(judge?.model).toLowerCase()
  if (
    provider === "openai" ||
    backend === "decisions" ||
    backend === "structured" ||
    provider.includes("openai")
  ) {
    return true
  }
  return model.includes("gpt-6") || model.startsWith("gpt-")
}

export function customerScoredBy(line: string): string {
  const text = trimText(line)
  if (!text) {
    return ""
  }
  if (isLegacyRunCopy(text)) {
    return OLDER_RUN_LABEL
  }
  if (/openai/i.test(text) && /couldn['’]t score/i.test(text)) {
    return text
  }
  if (/openai/i.test(text) || /via (?:vercel )?ai gateway/i.test(text)) {
    return "Scored by OpenAI Decisions"
  }
  if (/checks scored/i.test(text)) {
    return "Scored by Checks"
  }
  const match = text.match(/^(.+?) scored this run\.?$/i)
  if (match) {
    const name = match[1]
      .replace(/\s*\(your key\)/gi, "")
      .replace(/\s+via\s+.+$/i, "")
      .trim()
    return name ? `Scored by ${name}` : text
  }
  return text
}

export function scoredByFromJudge(judge: JudgeResult | null | undefined): string {
  if (!judge) {
    return ""
  }
  if (isOpenAIJudge(judge)) {
    return "Scored by OpenAI Decisions"
  }
  const provider = trimText(judge.provider).toLowerCase()
  const model = trimText(judge.model).toLowerCase()
  if (
    provider === "jev" ||
    provider === "evaluate" ||
    model.includes("jev") ||
    model.includes("typesafe") ||
    judge.status === "completed" ||
    (judge.answers && Object.keys(judge.answers).length > 0)
  ) {
    return "Scored by Checks"
  }
  return ""
}

export function scoredByLine(
  report?: Pick<Report, "scored_by" | "tasks"> | null
): string {
  const stamped = trimText(report?.scored_by)
  if (stamped) {
    return isLegacyRunCopy(stamped) ? OLDER_RUN_LABEL : customerScoredBy(stamped)
  }
  for (const task of report?.tasks ?? []) {
    const line = scoredByFromJudge(task.judge)
    if (line) {
      return line
    }
  }
  return ""
}

function cellWouldPass(id: string, choice: string): boolean {
  return PASS_LOCK[id]?.includes(choice.trim().toLowerCase()) ?? false
}

export function lowConfidenceWarning(task: TaskResult): string | null {
  if (workDidNotHappen(task)) {
    return null
  }
  const judge = task.judge
  const answers = judge?.answers
  if (!answers) {
    return null
  }
  const backend = trimText(judge?.backend).toLowerCase()
  if (backend === "structured") {
    return null
  }
  const openai = isOpenAIJudge(judge)
  if (!openai) {
    return null
  }
  let numeric: number | null = null
  let missing = false
  for (const id of CHECK_QUESTION_ORDER) {
    const answer: JudgeAnswer | undefined = answers[id]
    const choice = trimText(answer?.choice)
    if (!choice || !cellWouldPass(id, choice)) {
      continue
    }
    if (typeof answer?.confidence === "number") {
      if (answer.confidence < CONFIDENCE_WARN) {
        numeric =
          numeric == null ? answer.confidence : Math.min(numeric, answer.confidence)
      }
      continue
    }
    missing = true
  }
  if (numeric != null || missing) {
    return "The judge wasn't sure about this one"
  }
  return null
}

export function suiteUnsureWarning(
  report?: Pick<Report, "tasks"> | null
): string | null {
  for (const task of report?.tasks ?? []) {
    if (lowConfidenceWarning(task)) {
      return "The judge wasn't sure about this one"
    }
  }
  return null
}

export function openedCheckAnswers(task: TaskResult): OpenedAnswer[] {
  const answers = task.judge?.answers
  const cells = task.judge?.cells
  const hasAnswers = Boolean(
    answers && CHECK_QUESTION_ORDER.some((id) => id in answers)
  )
  const hasCells = Boolean(
    cells && CHECK_QUESTION_ORDER.some((id) => id in cells)
  )
  if (!hasAnswers && !hasCells) {
    return []
  }
  const unchecked = workDidNotHappen(task)
  return CHECK_QUESTION_ORDER.map((id) => {
    const question = task.judge?.questions?.[id]
    const choice =
      trimText(answers?.[id]?.choice) || trimText(cells?.[id]?.choice)
    return {
      id,
      label: trimText(question?.instructions) || CHECK_QUESTION_LABELS[id] || id,
      answer: unchecked ? "Not checked" : choice || "—",
    }
  })
}

function looksLikeDidntStart(text: string): boolean {
  const blob = text.toLowerCase()
  return (
    blob.includes("didn't start") ||
    blob.includes("didn't trigger") ||
    blob.includes("did not trigger") ||
    blob.includes("skill didn’t trigger") ||
    blob.includes("skill_trigger")
  )
}

function workDidNotHappen(task: TaskResult): boolean {
  if (task.passed === true) {
    return false
  }
  if (skillPathRan(task)) {
    return false
  }
  if (task.skipped) {
    return true
  }
  const blob = [
    happenedLine(task),
    ...(task.failures ?? []),
    trimText(task.judge?.reason),
    trimText(task.judge?.why),
    trimText(task.happened),
  ].join(" ")
  if (looksLikeDidntStart(blob)) {
    return true
  }
  const path = task.metrics?.path
  return Boolean(path && path.had_path === false)
}

/** True when stored path/spans/transcript show the skill actually ran. */
function skillPathRan(task: TaskResult): boolean {
  const path = task.metrics?.path
  if (path?.had_path) {
    return true
  }
  if (typeof path?.steps === "number" && path.steps > 0) {
    return true
  }
  for (const span of task.spans ?? []) {
    const name = span.name || ""
    if (name.startsWith("tool.") || name === "skill.select") {
      return true
    }
  }
  for (const line of (task.transcript ?? "").split("\n")) {
    const text = line.trim()
    if (!text.startsWith("{")) {
      continue
    }
    if (text.includes('"tool_call"') || text.includes('"skill.select"')) {
      return true
    }
  }
  return false
}

export function missingJudgeAnswersLine(task: TaskResult): string | null {
  if (openedCheckAnswers(task).length) {
    return null
  }
  const happened = happenedLine(task)
  const neverStarted =
    "The checker didn't score this check because the skill never started."
  const happenedIsGeneric =
    !happened || isGenericFail(happened) || isChecksDump(happened)
  if (!happenedIsGeneric) {
    if (looksLikeDidntStart(happened) && !skillPathRan(task)) {
      return neverStarted
    }
    if (/\b(timed out|timeout)\b/i.test(happened)) {
      return "The checker didn't score this check because it ran out of time."
    }
    return happened
  }
  const blob = [
    ...(task.failures ?? []),
    trimText(task.judge?.reason),
    trimText(task.judge?.why),
    happened,
  ]
    .join(" ")
    .toLowerCase()
  if (blob.includes("timed out") || blob.includes("timeout")) {
    return "The checker didn't score this check because it ran out of time."
  }
  if (looksLikeDidntStart(blob) && !skillPathRan(task)) {
    return neverStarted
  }
  if (task.skipped) {
    return "The checker didn't score this check because it was skipped."
  }
  return "The checker didn't score this check."
}

/** Path in opened details. Null means omit the row. */
export function pathOpenedLine(task: TaskResult): string | null {
  const caption = pathOpenedCaption(
    task.judge?.soft_answers?.path_efficiency?.choice,
    task.metrics
  )
  if (workDidNotHappen(task) && (caption || task.metrics?.path?.had_path === false)) {
    return "Not checked"
  }
  return caption
}

/** Gate already emits customer sentences. Rewrite leftover developer/warning codes. */
export function customerGateCopy(text: string): string {
  let value = trimText(text)
  if (!value) {
    return ""
  }
  value = value.replace(/\bSKILLGATE_TASK\b/g, "the task")
  if (FILE_WARN.test(value)) {
    return "This skill is meant to write a file, and this run didn't record one."
  }
  if (DRAFT_WARN.test(value)) {
    return "This run used the current checks, which aren't the saved Dataset yet."
  }
  if (NO_DATASET_WARN.test(value)) {
    return "This skill doesn't have a saved Dataset yet."
  }
  if (COVER_WARN.test(value)) {
    return "This run didn't include every check from the saved Dataset."
  }
  value = value.replace(/\bunlock Install\b/g, "unlock Deploy")
  value = value.replace(/\bInstall is unlocked\b/g, "Deploy is unlocked")
  if (/gate is red/i.test(value) || /clear gate green/i.test(value)) {
    return "Get a passing run to unlock Deploy."
  }
  if (/gate is green/i.test(value)) {
    return "Checks passed — Deploy is unlocked."
  }
  if (/missing golden/i.test(value) || /evals\/goldens/i.test(value)) {
    return "This check is missing its expected output file."
  }
  if (/BYO LLM returned 429/i.test(value) || /returned 429\b/.test(value)) {
    return "Your model provider refused the request (out of credit or rate-limited)."
  }
  if (
    /OPENAI_API_KEY or AI_GATEWAY_API_KEY/i.test(value) ||
    (/SKILLGATE_MODEL/.test(value) && /\.env/.test(value))
  ) {
    return "Check your key in Settings."
  }
  value = value.replace(/\bevals\/(?:goldens|fixtures)\/(\S+?)(?=[.,;:]?(?:\s|$))/gi, "$1")
  value = value.replace(/\bevals\/[\w./-]+/g, "the expected file")
  return scorerCodeToPlain(value)
}

export function hidePassFileWarning(
  warning: string,
  report?: Pick<Report, "tasks"> | null
): boolean {
  if (!FILE_WARN.test(warning)) {
    return false
  }
  const tasks = report?.tasks ?? []
  return tasks.some((task) => openedCheckAnswers(task).length > 0 && task.passed)
}

export function plainAdviceCopy(text?: string | null): string {
  let out = trimText(text)
  if (!out) {
    return ""
  }
  out = out.replace(/`description:`/g, "description")
  out = out.replace(/\bSKILL\.md\b/g, "the skill")
  out = out.replace(
    /\bThe agent only sees name \+ description(?: before opening (?:the skill|SKILL\.md))?\.?/gi,
    "Before it reads the instructions, the agent only sees the skill's name and description."
  )
  out = out.replace(
    /\bbefore opening the skill\b/gi,
    "before it reads the instructions"
  )
  out = out.replace(
    /\bdon['’]t switch to the good pdf[- ]?twin\b/gi,
    "don't switch to a working copy of this skill"
  )
  out = out.replace(/\bthe good pdf[- ]?twin\b/gi, "a working copy of this skill")
  out = out.replace(/\bthe a working copy\b/gi, "a working copy")
  out = out.replace(/,?\s*then run `?skillgate check`[^.]*\.?/gi, ".")
  out = out.replace(/\brun `?skillgate check`[^.]*\.?/gi, "")
  out = out.replace(/\s*`?skillgate check`\s*/g, " ")
  out = out.replace(
    /Replace the `description:` in the skill/gi,
    "Replace the skill's description"
  )
  out = out.replace(/`([^`]+)`/g, "$1")
  return out
}

/** Drop a heading that is repeated as the first sentence of the body. */
export function stripRepeatedHeadline(body?: string | null, headline?: string | null): string {
  const b = plainAdviceCopy(body)
  const h = plainAdviceCopy(headline)
  if (!h || !b.toLowerCase().startsWith(h.toLowerCase())) {
    return b
  }
  return b.slice(h.length).replace(/^[.\s:—–-]+/, "").trim()
}
