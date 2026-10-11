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

export function matchesSkill(
  skill: Pick<SkillPayload, "slug" | "id" | "absolute"> | null | undefined,
  key: string
): boolean {
  const needle = key.trim()
  if (!skill || !needle) {
    return false
  }
  return [skill.slug, skill.id, skill.absolute].some(
    (value) => (value || "").trim() === needle
  )
}

export function isSameSkill(
  current: SkillPayload | null,
  skillId: string,
  fallback?: SkillPayload
): boolean {
  if (matchesSkill(current, skillId)) {
    return true
  }
  if (!current || !fallback) {
    return false
  }
  return Boolean(
    (fallback.slug && fallback.slug === current.slug) ||
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

export function sidebarVersionLabel(
  status?: { version?: string | null } | null
): string {
  const version = status?.version?.trim()
  return version ? `v${version}` : "Skill Gate"
}

export function installedNote(
  skillName: string,
  lastDeploy: { semver?: string | null; target?: string | null }
): string {
  const ver = lastDeploy.semver ? ` v${lastDeploy.semver}` : ""
  const labeled = deployLabel(lastDeploy.target)
  const target = labeled ? ` to ${labeled}` : ""
  return `Installed ${skillName}${ver}${target}.`
}

export function collectChecksForRun(
  checks: Check[],
  skill: SkillPayload | null
): Check[] {
  return checks.map((check, index) => {
    const goldenPath = (check.golden_path || "").trim() || null
    const hasExpected = Boolean(
      (check.contains || "").toString().trim() || goldenPath
    )
    return {
      ...check,
      id: check.id || `check-${index + 1}`,
      prompt: check.prompt,
      should_trigger: check.should_trigger !== false,
      output_path:
        check.output_path || (hasExpected ? skillOutputPath(skill) : null),
      contains: check.contains || null,
      min_pages: check.min_pages || null,
      files: check.files || [],
      needs_upload: Boolean(check.needs_upload),
      golden_path: goldenPath,
      golden_kind: check.golden_kind || null,
    }
  })
}
