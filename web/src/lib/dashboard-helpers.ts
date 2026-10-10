import { ApiError } from "@/lib/api"
import { skillOutputPath } from "@/lib/types"
import type { Check, SkillPayload } from "@/lib/types"

export const SIGNED_OUT_CHECK =
  "You've been signed out. Sign in again to run this check."

export function asApiError(err: unknown): ApiError {
  if (err instanceof ApiError) {
    return err
  }
  if (err instanceof Error) {
    return new ApiError(err.message)
  }
  return new ApiError("Something went wrong.")
}

export function isSameSkill(
  current: SkillPayload | null,
  skillId: string,
  fallback?: SkillPayload
): boolean {
  if (!current) {
    return false
  }
  const currentIds = [current.absolute, current.id, current.name].filter(Boolean)
  if (currentIds.includes(skillId)) {
    return true
  }
  if (!fallback) {
    return false
  }
  return Boolean(
    (fallback.name && fallback.name === current.name) ||
      (fallback.id && fallback.id === current.id) ||
      (fallback.absolute && fallback.absolute === current.absolute)
  )
}

export function shouldSeedChecks(opts: {
  forceSeed?: boolean
  sameSkill: boolean
  checkCount: number
}): boolean {
  if (opts.forceSeed) {
    return true
  }
  if (opts.checkCount === 0) {
    return true
  }
  return !opts.sameSkill
}

export function uniqueCheckId(base: string, current: Check[]): string {
  const used = new Set(
    current.map((item) => item.id).filter((id): id is string => Boolean(id))
  )
  const trimmed = base.trim() || `check-${current.length + 1}`
  if (!used.has(trimmed)) {
    return trimmed
  }
  let n = 2
  while (used.has(`${trimmed}-${n}`)) {
    n += 1
  }
  return `${trimmed}-${n}`
}

export function deployLabel(target?: string | null) {
  const labels: Record<string, string> = {
    cursor: "Cursor",
    claude: "Claude",
    codex: "Codex",
    git: "git",
  }
  if (!target) {
    return null
  }
  return labels[target] ?? target
}

export function collectChecksForRun(
  checks: Check[],
  skill: SkillPayload | null
): Check[] {
  return checks.map((check, index) => ({
    id: check.id || `check-${index + 1}`,
    prompt: check.prompt,
    should_trigger: check.should_trigger !== false,
    output_path: check.output_path || (check.contains ? skillOutputPath(skill) : null),
    contains: check.contains || null,
    min_pages: check.min_pages || null,
    files: check.files || [],
    needs_upload: Boolean(check.needs_upload),
  }))
}
