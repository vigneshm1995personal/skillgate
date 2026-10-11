import {
  DEFAULT_OUTPUT_PATH,
  skillOutputPath,
  type Check,
  type CheckFile,
  type PackFile,
  type SkillPayload,
} from "@/lib/types"

export const MODEL_GENERATED_NOTICE =
  "These are model-generated (AI-generated). Edit them before Run."

export const STARTER_FROM_DESCRIPTION_NOTICE =
  "These are starter checks from your description. Edit them before Run."

export const BUNDLED_TEMPLATE_NOTICE =
  "Starter checks for this skill. Edit them before Run."

export const BUNDLED_SUITE_NOTICE =
  "These are the bundled suite checks. Edit them before Run."

export const PACK_BANK_NOTICE =
  "These checks are saved with this skill. Edit them, then press Run."

export const ASSIST_CHECKS_NOTICE =
  "Draft checks from Generate. Edit them before Run. They do not unlock Deploy until you save them."

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
