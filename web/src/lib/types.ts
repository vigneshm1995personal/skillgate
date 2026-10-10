import type { ConfigDiffEntry, EvalRunConfig, SupportedModelsMeta } from "@/lib/eval-config"

export type { ConfigDiffEntry, EvalRunConfig }

export type Stage = "home" | "eval" | "deploy" | "repository" | "history" | "settings"

export type EvalTab = "skill" | "checks" | "gate"

export type LiveHarnessId = "cursor-agent" | "codex" | "claude"

export type ResolvedHarnessId = LiveHarnessId | "llm"

export type HarnessPref = "auto" | LiveHarnessId

export function resolvedHarnessName(
  pref: HarnessPref,
  status?: { default_harness?: string | null } | null
): ResolvedHarnessId {
  if (pref === "cursor-agent" || pref === "codex" || pref === "claude") {
    return pref
  }
  if (status?.default_harness === "codex") {
    return "codex"
  }
  if (status?.default_harness === "claude") {
    return "claude"
  }
  if (status?.default_harness === "llm") {
    return "llm"
  }
  return "cursor-agent"
}

const LIVE_HARNESSES = new Set(["cursor-agent", "codex", "claude", "llm"])

export function isLiveHarness(name?: string | null): boolean {
  return LIVE_HARNESSES.has((name || "").toLowerCase())
}

export type CheckFile = {
  src: string
  dest: string
  path?: string
}

export type PackFile = {
  path: string
  bytes?: number
}

export type CaseBudgets = {
  tokens_total?: number | null
  max_steps?: number | null
}

export type Check = {
  id?: string
  prompt: string
  should_trigger?: boolean
  output_path?: string | null
  contains?: string | null
  min_pages?: number | null
  files?: CheckFile[]
  needs_upload?: boolean
  input?: string | null
  golden_path?: string | null
  golden_kind?: "json" | "text" | "bytes" | null
  bank_status?: "pinned" | "draft" | null
  budgets?: CaseBudgets | null
}

export type TaskMetrics = {
  path?: { steps?: number; errors?: number; had_path?: boolean }
  budgets?: CaseBudgets | null
  status?: "info" | "ok" | "fail"
  reasons?: string[]
  blocking?: boolean
}

export type DeployTarget = "cursor" | "claude" | "codex"

export type DeployMode = "local" | "git"

export type DeployAttempt = {
  id?: number
  run_id?: string | null
  skill_name?: string | null
  target: string
  status: string
  created_at?: string
  skill_version_id?: number | null
  semver?: string | null
  skill_md_hash?: string | null
  dest_path?: string | null
  error?: string | null
  pack_path?: string | null
  file_count?: number | null
  mode?: DeployMode | string | null
  url?: string | null
}

export type SkillVersion = {
  id?: number
  skill_name?: string
  semver?: string
  skill_md_hash?: string
  skill_path?: string
  created_at?: string
}

export type CatalogError = {
  message: string
  hint?: string
}

export type SkillPayload = {
  id: string
  name: string
  description?: string
  path?: string
  absolute: string
  uploaded?: boolean
  seed?: boolean
  sabotaged?: boolean
  semver?: string | null
  suite?: string | null
  gate?: string
  last_eval_at?: string | null
  eval_count?: number
  deploy_count?: number
  version_count?: number
  last_run?: RunRecord | null
  last_deploy?: DeployAttempt | null
  pack_files?: PackFile[]
  fixture_defaults?: Array<{ src: string; dest: string; bytes?: number }>
  default_output_path?: string | null
  has_dataset?: boolean
}

export const DEFAULT_OUTPUT_PATH = "output/result.txt"

export function skillOutputPath(skill?: SkillPayload | null): string {
  const named = String(skill?.default_output_path || "").trim()
  return named || DEFAULT_OUTPUT_PATH
}

export type TaskAdvice = {
  why?: string
  headline?: string
  change?: string
}

export type TaskScore = {
  scorer?: string
  passed?: boolean
  headline?: string
  detail?: string
  expected?: string | null
  actual?: string | null
}

export type Usage = {
  tokens_in?: number | null
  tokens_out?: number | null
  tokens_total?: number | null
  cost_usd?: number | null
}

export type JudgeQuestion = {
  type?: string
  instructions?: string
  criteria?: Record<string, string> | string[]
}

export type JudgeAnswer = {
  type?: string
  probability?: number
  choice?: string
  score?: number
  probabilities?: Record<string, number>
  reason?: string
  confidence?: number | null
}

export type JudgeUsage = {
  tokens_in?: number | null
  tokens_out?: number | null
  tokens_total?: number | null
  input_tokens?: number | null
  output_tokens?: number | null
  total_tokens?: number | null
  cost_usd?: number | null
}

export type JudgeCitationArtifact = {
  path?: string
  present?: boolean
}

export type JudgeResult = {
  status?: string
  reason?: string
  why?: string
  fail_reason?: string
  model?: string
  provider?: string
  backend?: string
  display_name?: string
  answers?: Record<string, JudgeAnswer>
  questions?: Record<string, JudgeQuestion>
  soft_answers?: Record<string, JudgeAnswer>
  soft_questions?: Record<string, JudgeQuestion>
  usage?: JudgeUsage | null
  passed?: boolean
  reasons?: string[]
  blocks_deploy?: boolean
  require_artifacts?: boolean
  skipped_questions?: string[]
  cells?: Record<string, { label?: string; choice?: string | null; reason?: string | null }>
  citations?: { artifacts?: JudgeCitationArtifact[] }
}

export type OtlpAttribute = {
  key: string
  value?: {
    stringValue?: string
    intValue?: string
    doubleValue?: number
    boolValue?: boolean
  }
}

export type OtlpSpan = {
  traceId?: string
  spanId?: string
  parentSpanId?: string
  name: string
  kind?: number
  startTimeUnixNano?: string
  endTimeUnixNano?: string
  status?: { code?: number; message?: string }
  attributes?: OtlpAttribute[]
}

export type BaselineRef = {
  run_id: string
  source: "deploy" | "manual"
  pack_fingerprint?: string | null
  suite?: string | null
  pinned_at?: string | null
  resolved?: boolean
}

export type VsBaseline = {
  verdict?:
    | "regressed"
    | "improved"
    | "stable"
    | "still_fail"
    | "new"
    | "dropped"
    | "skipped"
    | "uncomparable"
  hard?: boolean
  delta_tokens?: number | null
  delta_steps?: number | null
  cell_drops?: string[]
}

export type RegressionSummary = {
  comparable?: boolean
  hard?: boolean
  status?: "none" | "uncomparable" | "ok" | "regressed"
  reason?: string | null
  hard_ids?: string[]
  improved_ids?: string[]
  baseline_run_id?: string | null
  baseline_source?: "deploy" | "manual" | null
}

export type SkillUpdateKind = "fix" | "polish"
export type SkillUpdateTarget = "skill.md" | "scripts" | "references"

export type SkillUpdateEvidence = {
  check_id: string
  passed?: boolean | null
  cell?: string | null
  choice?: string | null
}

export type SkillUpdateItem = {
  id: string
  kind: SkillUpdateKind
  title: string
  detail?: string
  target: SkillUpdateTarget
  path?: string
  evidence?: SkillUpdateEvidence[]
}

export type SkillUpdatesPayload = {
  run_id: string
  skill?: string
  model?: string
  passed?: boolean | null
  gate_decision?: string | null
  gate_reason?: string | null
  summary?: string
  items: SkillUpdateItem[]
}

export type TaskResult = {
  id: string
  passed?: boolean | null
  status?: "queued" | "running" | "done"
  skipped?: boolean
  prompt?: string
  happened?: string
  expect_skill?: string | null
  selected_skill?: string | null
  failures?: string[]
  advice?: TaskAdvice
  transcript?: string
  files?: CheckFile[]
  scores?: TaskScore[]
  usage?: Usage | null
  judge?: JudgeResult | null
  spans?: OtlpSpan[] | null
  metrics?: TaskMetrics | null
  vs_baseline?: VsBaseline | null
}

export type LiveLine = {
  stream: string
  text: string
}

export type LiveState = {
  task_id?: string | null
  prompt?: string | null
  tail?: LiveLine[]
  /** Durable / synthesized mid-run transcript when in-process tail is empty. */
  transcript?: string | null
  spans?: OtlpSpan[] | null
  elapsed_sec?: number | null
  /** Server UTC start of the running check; UI ticks elapsed from it. */
  started_at?: string | null
  stalled?: boolean
  stall_reason?: "silent" | "repeating" | string | null
  silent_for_sec?: number | null
  repeat_count?: number
  last_line?: string | null
  output_count?: number
  skip_requested?: boolean
  kill_requested?: boolean
  tokens_in?: number | null
  tokens_out?: number | null
  tokens_total?: number | null
  cost_usd?: number | null
}

export type RunControlResponse = {
  ok: boolean
  action: "skip" | "kill" | string
  requested: boolean
  already: boolean
  status: string
}

export type Advice = {
  headline: string
  why: string
  change?: string
  paste: string
  demo_note?: string
  restore_scripts_from?: string | null
}

export type Report = {
  passed?: boolean | null
  passed_count: number
  task_count: number
  completed_count?: number
  current_task_id?: string | null
  skill: string
  suite?: string
  scored_by?: string
  harness?: string
  sandbox?: string
  title?: string
  tasks: TaskResult[]
  advice?: Advice | null
  skill_md_hash?: string
  semver?: string
  failed_task_ids?: string[]
  gate?: string | null
  config?: EvalRunConfig | null
  usage?: Usage | null
  metrics?: {
    budget_fails?: string[]
    status?: "info" | "ok" | "fail"
    path?: { steps?: number; errors?: number; had_path?: boolean }
  } | null
  regression?: RegressionSummary | null
  tryout?: boolean // never the Deploy source of record
}

export type RunError = {
  message: string
  hint?: string
}

export type RunRecord = {
  id?: string
  status: "running" | "done" | "error"
  /** Running row with no worker claim/progress lately (not live). */
  stale?: boolean
  idle_sec?: number | null
  passed?: boolean | null
  gate?: string | null
  gate_decision?: string
  gate_reason?: string
  gate_warnings?: string[]
  error?: RunError | null
  report?: Report | null
  live?: LiveState | null
  suite?: string | null
  skill?: string | null
  semver?: string | null
  skill_md_hash?: string | null
  skill_path?: string | null
  skill_version_id?: number | null
  created_at?: string
  harness?: string | null
  completed_count?: number
  task_count?: number
  current_task_id?: string | null
  config?: EvalRunConfig | null
  config_fingerprint?: string | null
  model?: string | null
  timeout_sec?: number | null
  temperature?: number | null
  reasoning_effort?: string | null
  config_changed?: boolean
  config_diff?: ConfigDiffEntry[]
  baseline?: BaselineRef | null
  regression?: RegressionSummary | null
  tryout?: boolean // never the Deploy source of record
}

export type TimelineItem = {
  kind: "run" | "deploy" | string
  id?: string
  at?: string
  label?: string
  passed?: boolean
  skill?: string
  semver?: string
  hash?: string
  harness?: string
  target?: string
  status?: string
  gate?: string
  config_label?: string
  config_fingerprint?: string | null
  config_changed?: boolean
  is_baseline?: boolean
  tryout?: boolean
}

export type HistoryPayload = {
  skill?: string | null
  gate: string
  last_run: RunRecord | null
  last_deploy: DeployAttempt | null
  versions: SkillVersion[]
  runs?: RunRecord[]
  deploys?: DeployAttempt[]
  timeline: TimelineItem[]
  baseline?: BaselineRef | null
}

export type AnalyticsRun = {
  id?: string
  skill?: string | null
  harness?: string | null
  passed?: boolean | null
  status?: string
  gate?: string | null
  created_at?: string
  tokens_total?: number | null
  cost_usd?: number | null
}

export type AnalyticsDeploy = {
  id?: number | string
  skill_name?: string | null
  target?: string | null
  status?: string | null
  created_at?: string | null
  semver?: string | null
}

export type AnalyticsPayload = {
  totals: {
    runs: number
    runs_7d: number
    runs_30d: number
    green: number
    red: number
    skills_evaluated: number
    skills_cleared: number
    deployments: number
  }
  usage: {
    runs_with_usage: number
    tokens_total: number | null
    cost_usd: number | null
  }
  recent_deploys?: AnalyticsDeploy[]
  recent: AnalyticsRun[]
  outcomes?: AnalyticsRun[]
}

export type SkillDetailPayload = {
  skill: SkillPayload
  gate: string
  last_run: RunRecord | null
  last_deploy: DeployAttempt | null
  versions: SkillVersion[]
  runs?: RunRecord[]
  deploys?: DeployAttempt[]
  timeline: TimelineItem[]
  pack_files?: PackFile[]
}

export type PackPreview = {
  path: string
  bytes: number
  kind: "text" | "image" | "pdf" | "binary"
  content_type?: string
  text?: string
}

export type DatasetFilePreview = {
  path?: string
  src?: string
  dest?: string
  bytes?: number
  kind?: string
  text?: string
  body?: string
  output_path?: string
  missing?: boolean
}

export type DatasetCase = {
  id: string
  status?: string
  prompt: string
  should_trigger?: boolean
  fixtures: DatasetFilePreview[]
  golden: DatasetFilePreview | null
}

export type DatasetView = {
  skill: string
  fingerprint?: string
  cases: DatasetCase[]
}

export type SiwvUser = {
  sub?: string | null
  name?: string | null
  email?: string | null
  preferred_username?: string | null
  picture?: string | null
}

export type AuthOpenReason = "qa" | "mini"

export type AuthMePayload = {
  auth_required: boolean
  user: SiwvUser | null
  denied?: boolean
  auth_open?: boolean
  auth_open_reason?: AuthOpenReason | null
}

export type ProductMode = "local" | "cloud"

export type FeatureSlots = {
  signIn?: boolean
  billing?: boolean
  sharedHistory?: boolean
  hostedJudge?: boolean
  sandboxes?: boolean
  tryoutCaps?: boolean
  generateChecks?: boolean
  gitPublish?: boolean
  suggestUpdates?: boolean
  analyticsHome?: boolean
}

export type StatusPayload = {
  version: string
  mode?: ProductMode
  slots?: FeatureSlots
  has_key: boolean
  has_gateway_key?: boolean
  live_backends: string[]
  available_harnesses?: LiveHarnessId[]
  default_harness?: ResolvedHarnessId
  missing_key_message?: string
  missing_key_hint?: string
  auth_required?: boolean
  siwv_configured?: boolean
  auth_open?: boolean
  auth_open_reason?: AuthOpenReason | null
  vercel_env?: string | null
  vercel_target_env?: string | null
  ci: {
    url: string
    badge: string
    workflow?: string
    conclusion?: string | null
  }
  deploy: {
    platforms: string[]
    live: string[]
    roots?: Record<string, string>
    modes?: DeployMode[]
    local_available?: boolean
    git?: {
      configured?: boolean
      repo_url?: string | null
      path_prefix?: string
      base_ref?: string
      open_pr?: boolean
      has_token?: boolean
    }
  }
  supported_models?: Record<string, string[]>
  supported_models_meta?: SupportedModelsMeta
  default_eval_config?: {
    model?: string | null
    timeout_sec?: number | null
    temperature?: number
    reasoning_effort?: string | null
  }
  harness_auth?: {
    has_cursor_api_key?: boolean
    has_codex_api_key?: boolean
    has_anthropic_api_key?: boolean
    has_gateway_api_key?: boolean
    selected_provider?: string
  }
  skills_dir_exists?: boolean
  skills_dir_count?: number
  catalog_error?: CatalogError | null
}

export type SettingsKeyId =
  | "CURSOR_API_KEY"
  | "CODEX_API_KEY"
  | "OPENAI_API_KEY"
  | "AI_GATEWAY_API_KEY"
  | "ANTHROPIC_API_KEY"

export type SettingsKeyPresence = {
  set: boolean
  from_vault: boolean
  from_env: boolean
}

export type SettingsKeysPayload = {
  keys: Record<SettingsKeyId, SettingsKeyPresence>
}

export type GenerateResponse = {
  skill: SkillPayload
  checks: Check[]
  yaml: string
  note?: string
  source?: "model" | "heuristic" | "template" | "suite" | "yaml" | "pack" | "assist" | "empty"
  warning?: string | null
  fixture_notice?: string | null
  fixture_defaults?: Array<{ src: string; dest: string; bytes?: number }>
}

export type FixtureBindResponse = {
  skill: SkillPayload
  checks: Check[]
  fixture_defaults?: Array<{ src: string; dest: string; bytes?: number }>
  inherit?: boolean
  glob?: string | null
}

export type PromoteDraft = {
  check: Check
  hints: string[]
  source_task_id?: string | null
  skill?: SkillPayload
  pack_files?: PackFile[]
}

export const CI_URL =
  "https://github.com/vigneshm1995personal/skillgate/actions"

export const MODEL_GENERATED_NOTICE =
  "These are model-generated (AI-generated). Edit them before Start."

export const STARTER_FROM_DESCRIPTION_NOTICE =
  "These are starter checks from your description. Edit them before Start."

export const BUNDLED_TEMPLATE_NOTICE =
  "Starter checks for this skill. Edit them before Start."

export const BUNDLED_SUITE_NOTICE =
  "These are the bundled suite checks. Edit them before Start."

export const PACK_BANK_NOTICE =
  "Deploy follows this Dataset. Generate drafts checks — doesn't unlock Deploy."

export const ASSIST_CHECKS_NOTICE =
  "Generate drafts checks — doesn't unlock Deploy."

export const FIXTURE_NOTICE =
  "Completion checks need a file in the skill folder — add input or keep trigger-only."

export const PACK_FIXTURE_NOTICE =
  "This skill has files you can use as check inputs."

export const NEEDS_UPLOAD_NOTICE =
  "This check needs input — paste facts, upload a file, or generate a sample."

export const START_NEEDS_UPLOAD =
  "Completion checks still need a file in the skill folder."

export const PACK_INHERIT_HINT =
  "Turn on Use pack fixtures, or add a file once to the skill folder."

export type StartBlockIssue = {
  index: number
  id: string
  label: string
}

const OUTPUT_HINT =
  /\b(extract|extracted|extraction|json|csv|yaml|save|saved|saving|files?|output|export|exported|dump)\b/i

const SEED_TEMPLATE_SKILLS = new Set(["pdf", "pdf-sabotaged"])

export function isDatasetPackPath(path: string, bytes?: number): boolean {
  const rel = path.replace(/\\/g, "/").replace(/^\//, "")
  if (!rel || rel === "SKILL.md") {
    return false
  }
  const lower = rel.toLowerCase()
  if (lower.endsWith(".md")) {
    return false
  }
  const suffix = lower.includes(".") ? lower.slice(lower.lastIndexOf(".")) : ""
  if (
    bytes != null &&
    ((suffix === ".pdf" && bytes < 100) ||
      ([".png", ".jpg", ".jpeg", ".gif", ".webp"].includes(suffix) &&
        bytes < 200))
  ) {
    return false
  }
  return lower.startsWith("evals/fixtures/") || lower.startsWith("assets/")
}

export function datasetPackFiles(files?: PackFile[] | null): PackFile[] {
  return (files || []).filter((item) =>
    isDatasetPackPath(item.path, item.bytes)
  )
}

export function authenticFixtureCopies(
  skill: SkillPayload | null,
  packFiles?: PackFile[] | null
): CheckFile[] {
  const defaults = skill?.fixture_defaults
  if (defaults?.length) {
    return defaults.map((item) => ({
      src: item.src,
      dest: item.dest,
    }))
  }
  return datasetPackFiles(packFiles ?? skill?.pack_files).map((item) => ({
    src: item.path,
    dest: item.path.split("/").pop() || item.path,
  }))
}

export function authenticFixtureDefaults(
  skill: SkillPayload | null,
  packFiles?: PackFile[] | null
): PackFile[] {
  const defaults = skill?.fixture_defaults
  if (defaults?.length) {
    return defaults.map((item) => ({
      path: item.src,
      bytes: item.bytes,
    }))
  }
  return datasetPackFiles(packFiles ?? skill?.pack_files)
}

export function startBlockedByNeedsUpload(
  checks: Check[],
  inherit: boolean,
  skill: SkillPayload | null
): boolean {
  return startBlockedIssues(checks, inherit, skill).length > 0
}

export function startBlockedIssues(
  checks: Check[],
  inherit: boolean,
  skill: SkillPayload | null
): StartBlockIssue[] {
  const copies = authenticFixtureCopies(skill)
  const bound = simulateInherit(checks, inherit, copies, skillOutputPath(skill))
  const issues: StartBlockIssue[] = []
  bound.forEach((check, index) => {
    if (!checkMissingRequiredFile(check)) {
      return
    }
    const id = String(check.id || "").trim()
    const label = `Check ${index + 1}`
    issues.push({ index: index + 1, id, label })
  })
  return issues
}

export function startBlockedMessage(
  checks: Check[],
  inherit: boolean,
  skill: SkillPayload | null
): string | null {
  const issues = startBlockedIssues(checks, inherit, skill)
  if (!issues.length) {
    return null
  }
  return issues
    .map((issue) => `${issue.label}: needs a file in the skill folder`)
    .join(". ")
}

export function checkNeedsInput(
  check: Check,
  inherit: boolean,
  skill: SkillPayload | null
): boolean {
  if (hasRealFixture(check.files)) {
    return false
  }
  if (check.should_trigger === false) {
    return false
  }
  const packHasFiles = authenticFixtureCopies(skill).length > 0
  if (
    inherit &&
    packHasFiles &&
    (isCompletionCheck(check) || check.needs_upload)
  ) {
    return false
  }
  return Boolean(check.needs_upload)
}

export function displayCheckFiles(
  check: Check,
  inherit: boolean,
  skill: SkillPayload | null
): CheckFile[] {
  if (hasRealFixture(check.files)) {
    return (check.files || []).filter((item) =>
      Boolean(String(item.src || "").trim() && String(item.dest || "").trim())
    )
  }
  if (check.should_trigger === false) {
    return []
  }
  if (!inherit) {
    return []
  }
  if (!isCompletionCheck(check) && !check.needs_upload) {
    return []
  }
  return authenticFixtureCopies(skill)
}

export function filesAreInherited(
  check: Check,
  inherit: boolean,
  skill: SkillPayload | null
): boolean {
  return (
    !hasRealFixture(check.files) &&
    displayCheckFiles(check, inherit, skill).length > 0
  )
}

function isCompletionCheck(check: Check): boolean {
  return Boolean(
    String(check.output_path || "").trim() ||
    String(check.contains || "").trim()
  )
}

function simulateInherit(
  checks: Check[],
  inherit: boolean,
  copies: CheckFile[],
  outputPath = DEFAULT_OUTPUT_PATH
): Check[] {
  const out = checks.map((check) => ({
    ...check,
    files: check.files ? [...check.files] : [],
  }))
  if (!inherit || copies.length === 0) {
    return out
  }
  if (!out.some(isCompletionCheck)) {
    const first = out.find((item) => item.should_trigger !== false)
    if (first && !isCompletionCheck(first)) {
      first.output_path = first.output_path || outputPath
    }
  }
  for (const item of out) {
    if (item.should_trigger === false) {
      continue
    }
    if (!isCompletionCheck(item) && item.needs_upload) {
      item.output_path = item.output_path || outputPath
    }
    if (!isCompletionCheck(item)) {
      continue
    }
    if (hasRealFixture(item.files)) {
      item.needs_upload = false
      continue
    }
    item.files = copies.map((copy) => ({ src: copy.src, dest: copy.dest }))
    item.needs_upload = false
  }
  return out
}

function checkMissingRequiredFile(check: Check): boolean {
  if (hasRealFixture(check.files)) {
    return false
  }
  if (check.needs_upload) {
    return true
  }
  return check.should_trigger === false && isCompletionCheck(check)
}

export function descriptionImpliesOutputs(
  description?: string | null
): boolean {
  return OUTPUT_HINT.test(description || "")
}

function hasRealFixture(files?: unknown[] | null): boolean {
  if (!files?.length) {
    return false
  }
  return files.some((item) => {
    if (!item || typeof item !== "object") {
      return false
    }
    const rec = item as { src?: unknown; dest?: unknown }
    return Boolean(
      String(rec.src || "").trim() && String(rec.dest || "").trim()
    )
  })
}

export function needsFixtureNotice(
  skill: SkillPayload | null,
  checks: Check[]
): boolean {
  if (!skill || SEED_TEMPLATE_SKILLS.has(skill.name)) {
    return false
  }
  if (datasetPackFiles(skill.pack_files).length) {
    return !checks.some(
      (check) =>
        Boolean(check.output_path || check.contains) &&
        hasRealFixture(check.files)
    )
  }
  if (!descriptionImpliesOutputs(skill.description)) {
    return false
  }
  return !checks.some(
    (check) =>
      Boolean(check.output_path || check.contains) &&
      hasRealFixture(check.files)
  )
}

export const PASTE_PLACEHOLDER = `---
name: my-skill
description: Extract text from PDFs and merge documents. Use when the user mentions a .pdf file, invoices, or combining files.
---

# Steps
1. Read the input files
2. Write the result under output/`
