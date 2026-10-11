export type SkillDetailStatus = "loading" | "error" | "ready"

/** Skill cards/lists leave the skeleton as soon as the skill request settles. */
export function skillDetailStatus(opts: {
  skillSettled: boolean
  error: string
}): SkillDetailStatus {
  if (!opts.skillSettled) {
    return "loading"
  }
  if (opts.error) {
    return "error"
  }
  return "ready"
}
