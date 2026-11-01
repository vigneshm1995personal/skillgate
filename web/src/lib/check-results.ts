import { isJudgeScorerCopy, isLegacyRunCopy, JUDGE_SCORED, OLDER_RUN_LABEL } from "@/lib/eval-config"
import { pathOpenedCaption } from "@/lib/metrics-label"
import type { JudgeAnswer, JudgeQuestion, JudgeResult, Report, TaskResult } from "@/lib/types"

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
  path_efficiency: "How it ran",
}

const PASS_LOCK: Record<string, string[]> = {
  task_completion: ["fully completed"],
  correctness: ["correct", "mostly correct"],
  instruction_adherence: ["fully followed", "minor deviation"],
  evidence_action_validity: ["fully supported", "partially supported", "n/a"],
  result_quality: ["clear and complete", "mostly good"],
}

const CHOICE_SCORES: Record<string, Record<string, number>> = {
  task_completion: {
    "fully completed": 1,
    "partially completed": 0.5,
    "not completed": 0,
  },
  correctness: {
    correct: 1,
    "mostly correct": 0.75,
    "insufficient evidence": 0.5,
    incorrect: 0,
  },
  instruction_adherence: {
    "fully followed": 1,
    "minor deviation": 0.75,
    "major deviation": 0.25,
    violated: 0,
  },
  evidence_action_validity: {
    "fully supported": 1,
    "partially supported": 0.75,
    "n/a": 1,
    unsupported: 0,
  },
  result_quality: {
    "clear and complete": 1,
    "mostly good": 0.75,
    "significant issues": 0.25,
    poor: 0,
  },
  path_efficiency: {
    efficient: 1,
    acceptable: 0.75,
    looping: 0.25,
    wasteful: 0,
  },
}

const PREDICATE_PASS = 0.8
const RUBRIC_TEXTS = new Set(
  [
    "The test's expected outcome is fully met.",
    "Some of the requested work is done but incomplete.",
    "The requested work was not done.",
    "The result matches the expected outcome.",
    "Core claims are right with minor errors.",
    "The result is wrong.",
    "The delivered result is clear and complete.",
    "Mostly good with minor quality gaps (still Pass).",
    "Significant quality issues (Fail).",
    "Poor quality result (Fail).",
    "The skill took a direct path: no repeated tool calls, no loops, no wasted steps.",
    "The skill finished with only minor extra steps and no looping.",
    "The skill repeated the same or near-same tool calls without making progress.",
    "The skill spent many tool calls off-task or thrashing.",
  ].map((item) => item.toLowerCase())
)

export const CONFIDENCE_WARN = 0.5
export const UNSURE_REVIEW = "unsure, needs review"
export const NO_REASON_RECORDED = "No reason recorded"
export const WORDING_OVERRIDE_NOTE =
  "Wording check passed, so those Fail rows did not turn the gate red."
export const GUARD_REFUSED_RETRY_NOTE =
  "A second refund attempt was refused. Only one refund went through."

const CANNED_WHY_REASONS = new Set(
  [
    "This run finished the customer request.",
    "This run left the customer request unfinished.",
    "This run did not attempt the customer request.",
    "The facts on this run are right.",
    "The facts on this run are wrong.",
    "The facts on this run only partly match.",
    "This run followed the skill's rules.",
    "This run broke a skill rule.",
    "No skill rule applied on this run.",
    "This run's tool use is allowed.",
    "This run's tool use is not allowed.",
    "This run needed no extra tool use.",
    "The customer reply on this run is clear.",
    "The customer reply on this run is not clear.",
    "This run's path was efficient.",
    "This run's path wasted steps.",
    "No short evidence line from this run.",
  ].map((item) => item.toLowerCase())
)

const CHECKS_DUMP = /^Checks:\s+/i
const GENERIC_FAIL = "This check did not pass."
const CHECKS_PLAIN = /^Checks:\s+(\w+)\s+(.+?)(?:\s+\(need\s+(.+?)\))?(?:\s+[—–-]\s+(.*))?$/i
const SCORER_CODE =
  /^(?:Checks:\s+)?([a-z_]+)\s+([a-z0-9_-]+)(?:\s+\(need\s+([a-z0-9_-]+)\))?$/i
const SKILL_DIDNT_START =
  "The skill didn't start for this request — its description doesn't match what was asked."
const TRIGGER_SECONDARY_NOTE =
  "Note: this skill wasn't opened during this run. If it should have been, you can review the description."
const FILE_WARN =
  /did not finish a file this skill is supposed to write|meant to write a file/i
const DRAFT_WARN = /used draft checks, not the saved Dataset/i
const NO_DATASET_WARN = /this skill has no saved Dataset/i
const COVER_WARN = /did not cover the saved Dataset/i

export type OpenedAnswer = {
  id: string
  label: string
  answer: string
  score?: number
  reason?: string
  source?: string
  passed?: boolean | null
}

function trimText(value: unknown): string {
  return typeof value === "string" ? value.trim() : ""
}

export function checkSource(value: unknown): string | undefined {
  const raw = trimText(value).toLowerCase()
  if (raw === "text" || raw === "log/text" || raw === "from the log/text") {
    return "from the log/text"
  }
  if (raw === "log" || raw === "from the log") {
    return "from the log"
  }
  if (raw === "judge" || raw === "from the judge") {
    return "from the judge"
  }
  return undefined
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

function reservedQuestionId(id: string): boolean {
  return (
    (CHECK_QUESTION_ORDER as readonly string[]).includes(id) ||
    id === "path_efficiency" ||
    id.endsWith("_why")
  )
}

function extraFailureTexts(task: TaskResult): string[] {
  const extras = task.judge?.extra_failures
  if (!Array.isArray(extras)) {
    return []
  }
  return extras.map((item) => trimText(item)).filter(Boolean)
}

export function behaviorQuestionIds(task: TaskResult): string[] {
  const extras = extraFailureTexts(task)
  const cells = task.judge?.cells ?? {}
  const questions = task.judge?.questions ?? {}
  const found: string[] = []
  const add = (id: string) => {
    const name = trimText(id)
    if (name && !found.includes(name) && !reservedQuestionId(name)) {
      found.push(name)
    }
  }
  for (const text of extras) {
    let matched = false
    for (const [id, cell] of Object.entries(cells)) {
      if (trimText(cell?.reason) === text) {
        add(id)
        matched = true
        break
      }
    }
    if (!matched) {
      for (const [id, question] of Object.entries(questions)) {
        const ask = trimText(question?.instructions)
        if (ask && (text === `${ask} No` || text.startsWith(ask))) {
          add(id)
          matched = true
          break
        }
      }
    }
    if (!matched) {
      add(text.replace(/\s+No$/i, "").trim() || text)
    }
  }
  return found
}

export function behaviorFailLine(question: string): string {
  return `The agent's behavior failed this check: ${question} → No. Review the run log below.`
}

function skillWasNotOpened(task: TaskResult): boolean {
  if (skillPathRan(task)) {
    return false
  }
  const selected = trimText(task.selected_skill).toLowerCase()
  return !selected || selected === "none"
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
  const key = trimText(match[1]).toLowerCase()
  const label = CHECK_QUESTION_LABELS[key]
  const choice = trimText(match[2]).replace(/\s+\(need\s+.+\)$/i, "")
  if (label && choice && afterDash) {
    return `${label} ${choice} — ${afterDash}`
  }
  if (afterDash) {
    return afterDash
  }
  if (label && choice) {
    return `${label} ${choice}.`
  }
  const rest = text.replace(CHECKS_DUMP, "").trim()
  return rest ? scorerCodeToPlain(rest, hint) : null
}

export function caseRowTitle(task: {
  id?: string | null
  name?: string | null
  prompt?: string | null
}): string {
  const name = trimText(task.name)
  if (name) {
    return name
  }
  const id = trimText(task.id)
  if (id) {
    return id
  }
  return checkHeadline(task)
}

export function caseScenario(task: {
  scenario?: string | null
  setup?: string | null
  prompt?: string | null
}): string {
  return trimText(task.scenario) || trimText(task.setup) || trimText(task.prompt)
}

export function formatCheckScore(value: unknown): string {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return ""
  }
  return value.toFixed(2)
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
  if (task.status === "queued") {
    return "Queued"
  }
  if (task.status === "running") {
    return "In progress"
  }
  const passedClean =
    task.passed === true && task.review !== true && task.status !== "unsure"
  if (passedClean) {
    const stampedPass = trimText(task.happened)
    if (
      stampedPass &&
      stampedPass !== UNSURE_REVIEW &&
      !isGenericFail(stampedPass) &&
      !isChecksDump(stampedPass)
    ) {
      return scorerCodeToPlain(stampedPass, hint)
    }
    if (task.expect_skill === null && !task.selected_skill) {
      return "No skill was picked, as expected."
    }
    return "Output matched what was expected."
  }
  if (
    (task.review === true || task.status === "unsure") &&
    task.passed !== false
  ) {
    return UNSURE_REVIEW
  }
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
  const behavior = behaviorQuestionIds(task)
  if (behavior.length) {
    return behaviorFailLine(behavior[0])
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
  const behavior = behaviorQuestionIds(task)
  if (behavior.length) {
    return skillWasNotOpened(task) ? TRIGGER_SECONDARY_NOTE : null
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

function customerScorerName(judge: JudgeResult | null | undefined): string {
  const provider = trimText(judge?.provider).toLowerCase()
  if (provider === "skip") {
    return "Checks"
  }
  const name = trimText(judge?.display_name)
  if (name === "Checks") {
    return "Checks"
  }
  if (
    name === "Other" ||
    name.toLowerCase() === "your judge" ||
    provider === "compatible" ||
    provider === "other"
  ) {
    return "your judge"
  }
  return "the judge"
}

export function customerScoredBy(line: string): string {
  const text = trimText(line)
  if (!text) {
    return ""
  }
  if (isLegacyRunCopy(text)) {
    return OLDER_RUN_LABEL
  }
  if (/^scored by the judge\b/i.test(text)) {
    return JUDGE_SCORED
  }
  if (/^scored by (other|your judge)\b/i.test(text)) {
    return "Scored by your judge"
  }
  if (/^scored by (jev|clef|openai|aws)\b/i.test(text)) {
    return JUDGE_SCORED
  }
  if (/^scored by checks\b/i.test(text)) {
    return "Scored by Checks"
  }
  if (/couldn['’]t score/i.test(text)) {
    return text
      .replace(/OpenAI Decisions( couldn't score this run)?/gi, (_match, tail) =>
        tail ? "The judge couldn't score this run" : "the judge"
      )
      .replace(/^OpenAI couldn't score this run/i, "The judge couldn't score this run")
      .replace(/Your OpenAI account is out of credits/gi, "This account is out of credits")
      .replace(/\bOpenAI\b/g, "the judge")
      .replace(/\bJev\b/g, "the judge")
      .replace(/\bClef\b/g, "the judge")
      .replace(/\bAWS\b/g, "the judge")
      .replace(/\bCloudflare\b/gi, "the judge")
  }
  if (isJudgeScorerCopy(text) || /via (?:vercel )?ai gateway/i.test(text)) {
    return JUDGE_SCORED
  }
  if (/checks scored/i.test(text)) {
    return "Scored by Checks"
  }
  if (/quality was not scored/i.test(text)) {
    return "Quality was not scored"
  }
  const match = text.match(/^(.+?) scored this run\.?$/i)
  if (match) {
    const name = match[1]
      .replace(/\s*\(your key\)/gi, "")
      .replace(/\s+via\s+.+$/i, "")
      .trim()
    if (!name || isJudgeScorerCopy(name) || /decisions|gateway/i.test(name)) {
      return JUDGE_SCORED
    }
    return `Scored by ${name}`
  }
  return text
}

export function scoredByFromJudge(judge: JudgeResult | null | undefined): string {
  if (!judge) {
    return ""
  }
  const provider = trimText(judge.provider).toLowerCase()
  if (provider === "skip" || judge.status === "skip") {
    return "Quality was not scored"
  }
  const name = customerScorerName(judge)
  if (judge.status === "error") {
    const who = name === "the judge" ? "The judge" : name
    return `${who} couldn't score this run.`
  }
  if (
    judge.status === "completed" ||
    (judge.answers && Object.keys(judge.answers).length > 0)
  ) {
    return name === "the judge" ? "Scored by the judge" : `Scored by ${name}`
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

function clampScore(value: number): number {
  if (value < 0) return 0
  if (value > 1) return value <= 10 ? value / 10 : 1
  return value
}

function choiceOutcomeScore(id: string, choice: string): number | undefined {
  const mapped = CHOICE_SCORES[id]?.[choice.trim().toLowerCase()]
  return typeof mapped === "number" ? mapped : undefined
}

function answerScore(
  id: string,
  choice: string,
  answer?: JudgeAnswer | null,
  cell?: { probability?: number; confidence?: number; score?: number } | null,
  listed?: { score?: number } | null
): number | undefined {
  for (const value of [answer?.probability, cell?.probability, answer?.score, cell?.score]) {
    if (typeof value === "number" && !Number.isNaN(value)) {
      return clampScore(value)
    }
  }
  const mapped = choiceOutcomeScore(id, choice)
  if (mapped != null) return mapped
  const guessed = cellWouldPass(id, choice)
  if (guessed != null) return guessed ? 1 : 0
  if (typeof listed?.score === "number" && !Number.isNaN(listed.score)) {
    return clampScore(listed.score)
  }
  return undefined
}

function cellWouldPass(id: string, choice: string): boolean | null {
  const text = choice.trim().toLowerCase()
  if (!text) return null
  if (PASS_LOCK[id]) {
    return PASS_LOCK[id].includes(text)
  }
  if (id === "path_efficiency") {
    if (text === "efficient" || text === "acceptable") return true
    if (text in (CHOICE_SCORES.path_efficiency || {})) return false
    return null
  }
  if (["yes", "pass", "true", "1"].includes(text)) return true
  if (["no", "fail", "false", "0"].includes(text)) return false
  return null
}

function reasonRepeatsPrompt(label: string, choice: string, reason: string): boolean {
  const compact = reason.trim().replace(/\s+/g, " ")
  const ask = label.trim().replace(/\s+/g, " ")
  if (!compact) return true
  if (ask && compact === ask) return true
  if (choice && compact.toLowerCase() === choice.trim().toLowerCase()) return true
  if (ask && choice && compact === `${ask} ${choice}`.trim()) return true
  if (
    ask &&
    compact.toLowerCase().startsWith(ask.toLowerCase()) &&
    (!choice || compact.toLowerCase().endsWith(choice.trim().toLowerCase()))
  ) {
    return true
  }
  return false
}

function isBuiltReason(reason: string): boolean {
  const text = reason.trim()
  if (!text) return false
  const compact = text.toLowerCase().replace(/\.+$/, "")
  if (CANNED_WHY_REASONS.has(text.toLowerCase()) || CANNED_WHY_REASONS.has(`${compact}.`)) {
    return true
  }
  if (
    text.startsWith("Connector calls:") ||
    text.startsWith("The agent replied:") ||
    text.startsWith("Expected outcome:") ||
    text.startsWith("No short evidence")
  ) {
    return true
  }
  return (
    text.includes(" on this run. Connector") || text.includes(" on this run. Reply:")
  )
}

function isCleanPass(task: TaskResult): boolean {
  return (
    task.passed === true &&
    task.review !== true &&
    task.status !== "unsure" &&
    task.judge?.review !== true
  )
}

function isHardFail(task: TaskResult): boolean {
  return task.passed === false
}

export function wordingOverrideNote(task: TaskResult): string | null {
  const warnings = task.judge?.warnings
  if (!Array.isArray(warnings)) {
    return null
  }
  return warnings.some((item) => String(item).trim() === WORDING_OVERRIDE_NOTE)
    ? WORDING_OVERRIDE_NOTE
    : null
}

export function refusedRetryNote(task: TaskResult): string | null {
  const warnings = task.judge?.warnings
  if (!Array.isArray(warnings)) {
    return null
  }
  return warnings.some((item) => String(item).trim() === GUARD_REFUSED_RETRY_NOTE)
    ? GUARD_REFUSED_RETRY_NOTE
    : null
}

function isRubricReason(
  reason: string,
  question?: JudgeQuestion | null
): boolean {
  const text = reason.trim()
  if (!text) return false
  if (RUBRIC_TEXTS.has(text.toLowerCase())) return true
  const criteria = question?.criteria
  if (criteria && typeof criteria === "object" && !Array.isArray(criteria)) {
    return Object.values(criteria).some(
      (value) => typeof value === "string" && value.trim() === text
    )
  }
  return false
}

function openedReason(
  _task: TaskResult,
  _id: string,
  choice: string,
  label: string,
  answer?: JudgeAnswer | null,
  cell?: { reason?: string | null } | null,
  listed?: { reason?: string } | null,
  question?: JudgeQuestion | null
): string {
  const texts = [
    trimText(answer?.reason),
    trimText(cell?.reason),
    trimText(listed?.reason),
  ].filter(Boolean)
  for (const text of texts) {
    if (isRubricReason(text, question)) continue
    if (isBuiltReason(text)) continue
    if (reasonRepeatsPrompt(label, choice, text)) continue
    return text
  }
  return NO_REASON_RECORDED
}

function openedPassed(
  id: string,
  choice: string,
  score: number | undefined,
  cell?: { passed?: boolean; status?: string } | null,
  listed?: { passed?: boolean } | null
): boolean | null {
  if (typeof cell?.passed === "boolean") return cell.passed
  if (typeof listed?.passed === "boolean") return listed.passed
  const guessed = cellWouldPass(id, choice)
  if (guessed != null) return guessed
  if (score != null) return score >= PREDICATE_PASS
  return null
}

function hasConfidenceChannel(judge: JudgeResult | null | undefined): boolean {
  if (judge?.supports_confidence === true) {
    return true
  }
  if (judge?.supports_confidence === false) {
    return false
  }
  const backend = trimText(judge?.backend).toLowerCase()
  if (["structured", "responses", "aws", "jev", "clef", "skip"].includes(backend)) {
    return false
  }
  const provider = trimText(judge?.provider).toLowerCase()
  if (provider === "jev" || provider === "clef" || provider === "aws" || provider === "skip") {
    return false
  }
  return provider === "openai" || backend === "decisions"
}

export function lowConfidenceWarning(task: TaskResult): string | null {
  if (isCleanPass(task) || isHardFail(task) || workDidNotHappen(task)) {
    return null
  }
  const judge = task.judge
  const answers = judge?.answers
  if (!answers) {
    return null
  }
  if (!hasConfidenceChannel(judge)) {
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
  if (task.review || task.status === "unsure") {
    return UNSURE_REVIEW
  }
  if (numeric != null || missing) {
    return UNSURE_REVIEW
  }
  return null
}

export function suiteUnsureWarning(
  report?: Pick<Report, "tasks" | "gate" | "passed"> | null
): string | null {
  if (report?.gate === "needs review") {
    return UNSURE_REVIEW
  }
  if (
    report?.gate === "green" ||
    report?.gate === "red" ||
    report?.passed === true ||
    report?.passed === false
  ) {
    return null
  }
  for (const task of report?.tasks ?? []) {
    if (lowConfidenceWarning(task)) {
      return UNSURE_REVIEW
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
  const listed = Array.isArray(task.check_answers) ? task.check_answers : []
  const extraKeys = [
    ...Object.keys(answers ?? {}),
    ...Object.keys(cells ?? {}),
    ...Object.keys(task.judge?.questions ?? {}),
  ].some((id) => !reservedQuestionId(id))
  if (!hasAnswers && !hasCells && !extraKeys && listed.length === 0) {
    return []
  }
  const unchecked = workDidNotHappen(task)
  const failedBehavior = new Set(behaviorQuestionIds(task))
  const stampOpened = (
    id: string,
    row: OpenedAnswer,
    choice: string,
    answer?: JudgeAnswer | null,
    cell?: {
      probability?: number
      confidence?: number
      score?: number
      reason?: string | null
      passed?: boolean
      status?: string
    } | null,
    listedRow?: { score?: number; reason?: string; passed?: boolean } | null,
    question?: JudgeQuestion | null
  ): OpenedAnswer => {
    const score = answerScore(id, choice, answer, cell, listedRow)
    if (score != null) row.score = score
    const reason = openedReason(
      task,
      id,
      choice,
      row.label,
      answer,
      cell,
      listedRow,
      question
    )
    if (reason) row.reason = reason
    const passed = openedPassed(id, choice, score, cell, listedRow)
    if (passed != null) row.passed = passed
    return row
  }
  const builtins = CHECK_QUESTION_ORDER.map((id) => {
    const question = task.judge?.questions?.[id]
    const choice =
      trimText(answers?.[id]?.choice) || trimText(cells?.[id]?.choice)
    const unsure =
      !isCleanPass(task) && !isHardFail(task) && cells?.[id]?.status === "unsure"
    const listedRow = listed.find(
      (row) => trimText(row?.id) === id || trimText(row?.label) === (CHECK_QUESTION_LABELS[id] || "")
    )
    const row: OpenedAnswer = {
      id,
      label: trimText(question?.instructions) || CHECK_QUESTION_LABELS[id] || id,
      answer: unchecked
        ? "Not checked"
        : unsure
          ? UNSURE_REVIEW
          : choice || "—",
      source: checkSource(
        answers?.[id]?.source ||
          cells?.[id]?.source ||
          listedRow?.source_label ||
          listedRow?.source ||
          "judge"
      ),
    }
    return stampOpened(id, row, choice, answers?.[id], cells?.[id], listedRow, question)
  })
  const seen = new Set<string>(CHECK_QUESTION_ORDER)
  const extras: OpenedAnswer[] = []
  const pathChoice =
    trimText(answers?.path_efficiency?.choice) ||
    trimText(cells?.path_efficiency?.choice) ||
    trimText(task.judge?.soft_answers?.path_efficiency?.choice)
  if (
    !unchecked &&
    (pathChoice || cells?.path_efficiency || answers?.path_efficiency)
  ) {
    seen.add("path_efficiency")
    const listedRow = listed.find(
      (row) =>
        trimText(row?.id) === "path_efficiency" ||
        trimText(row?.label) === "How it ran"
    )
    const pathCell = cells?.path_efficiency
    extras.push(
      stampOpened(
        "path_efficiency",
        {
          id: "path_efficiency",
          label: "How it ran",
          answer: unchecked ? "Not checked" : pathChoice || "—",
          source: checkSource(
            answers?.path_efficiency?.source ||
              pathCell?.source ||
              listedRow?.source_label ||
              listedRow?.source ||
              "judge"
          ),
        },
        pathChoice,
        answers?.path_efficiency || task.judge?.soft_answers?.path_efficiency,
        pathCell,
        listedRow,
        task.judge?.questions?.path_efficiency || task.judge?.soft_questions?.path_efficiency
      )
    )
  } else {
    seen.add("path_efficiency")
  }
  const extraIds = [
    ...Object.keys(answers ?? {}),
    ...Object.keys(cells ?? {}),
    ...Object.keys(task.judge?.questions ?? {}),
  ]
  for (const id of extraIds) {
    if (seen.has(id) || reservedQuestionId(id)) {
      continue
    }
    seen.add(id)
    const question = task.judge?.questions?.[id]
    const cell = cells?.[id]
    const probability =
      typeof answers?.[id]?.probability === "number"
        ? answers[id].probability
        : typeof cell?.probability === "number"
          ? cell.probability
          : null
    const choice =
      trimText(answers?.[id]?.choice) ||
      trimText(cell?.choice) ||
      (probability === null ? "" : String(probability))
    const extra: OpenedAnswer = {
      id,
      label:
        trimText(question?.instructions) ||
        trimText(cell?.label) ||
        id,
      answer: unchecked && !failedBehavior.has(id) ? "Not checked" : choice || "—",
    }
    const listedRow = listed.find(
      (row) =>
        trimText(row?.label) === extra.label ||
        trimText(row?.id) === id
    )
    const source = checkSource(
      answers?.[id]?.source ||
        cell?.source ||
        listedRow?.source_label ||
        listedRow?.source
    )
    if (source) {
      extra.source = source
    }
    extras.push(
      stampOpened(id, extra, choice, answers?.[id], cell, listedRow, question)
    )
  }
  const builtinLabels = new Set(Object.values(CHECK_QUESTION_LABELS))
  for (const [index, row] of listed.entries()) {
    const label = trimText(row?.label)
    if (
      !label ||
      extras.some((item) => item.label === label) ||
      builtinLabels.has(label) ||
      reservedQuestionId(trimText(row?.id))
    ) {
      continue
    }
    const source = checkSource(row?.source_label || row?.source)
    const listedChoice = trimText(row?.answer)
    extras.push(
      stampOpened(
        trimText(row?.id) || `listed-${index}`,
        {
          id: trimText(row?.id) || `listed-${index}`,
          label,
          answer: listedChoice || "—",
          ...(source ? { source } : {}),
        },
        listedChoice,
        null,
        null,
        row,
        null
      )
    )
  }
  return [...builtins, ...extras]
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
