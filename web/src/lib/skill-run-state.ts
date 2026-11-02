import { isLiveHarness, type Check, type RunRecord, type SkillPayload } from "@/lib/types"

/** Shown on single-check try-outs. Never the Deploy source of record. */
export const TRYOUT_LABEL = "Single check — doesn't change Deploy"

export type RunPurpose = "gate" | "tryout"

export type SkillRunSlot = {
  gate: RunRecord | null
  tryout: RunRecord | null
  pin: RunRecord | null
  runningPurpose: RunPurpose | null
}

export function emptySkillRunSlot(): SkillRunSlot {
  return {
    gate: null,
    tryout: null,
    pin: null,
    runningPurpose: null,
  }
}

export function skillSlotKey(
  skill?: Pick<SkillPayload, "slug" | "id" | "name"> | string | null
): string {
  if (!skill) {
    return ""
  }
  if (typeof skill === "string") {
    return skill.trim()
  }
  return (skill.slug || skill.id || skill.name || "").trim()
}

export function isTryoutRun(
  record: Pick<RunRecord, "tryout" | "report"> | null | undefined
): boolean {
  if (!record) {
    return false
  }
  if (record.tryout) {
    return true
  }
  return Boolean(record.report?.tryout)
}

export function runSkillName(
  record: Pick<RunRecord, "skill" | "report"> | null | undefined
): string {
  return (record?.report?.skill || record?.skill || "").trim()
}

export function pinBelongsToSkill(
  pin: RunRecord | null | undefined,
  skillName?: string | null
): boolean {
  const name = (skillName || "").trim()
  if (!name || !pin) {
    return false
  }
  const pinSkill = runSkillName(pin)
  return !pinSkill || pinSkill === name
}

export function isViewingOlderRun(
  slot: SkillRunSlot,
  skillName?: string | null
): boolean {
  if (!pinBelongsToSkill(slot.pin, skillName)) {
    return false
  }
  const pinId = (slot.pin?.id || "").trim()
  if (!pinId) {
    return false
  }
  const liveId = (liveGateRun(slot, skillName)?.id || "").trim()
  if (!liveId) {
    return false
  }
  return pinId !== liveId
}

export function shownGateRun(slot: SkillRunSlot, skillName?: string | null): RunRecord | null {
  if (pinBelongsToSkill(slot.pin, skillName)) {
    return slot.pin
  }
  const gate = slot.gate
  if (!gate || isTryoutRun(gate)) {
    return null
  }
  const name = (skillName || "").trim()
  if (name && runSkillName(gate) && runSkillName(gate) !== name) {
    return null
  }
  return gate
}

export function liveGateRun(slot: SkillRunSlot, skillName?: string | null): RunRecord | null {
  const gate = slot.gate
  if (!gate || isTryoutRun(gate)) {
    return null
  }
  const name = (skillName || "").trim()
  if (name && runSkillName(gate) && runSkillName(gate) !== name) {
    return null
  }
  return gate
}

export function deployAllowedForLiveGate(opts: {
  skill: Pick<SkillPayload, "slug" | "id" | "name"> | null | undefined
  liveGate: RunRecord | null | undefined
  gateRunning: boolean
  mode?: "local" | "cloud" | null
  hasKey?: boolean
}): boolean {
  const { skill, liveGate, gateRunning, mode, hasKey } = opts
  if (hasKey === false) {
    return false
  }
  if (gateRunning || !skill || !liveGate) {
    return false
  }
  if (isTryoutRun(liveGate)) {
    return false
  }
  if (liveGate.status === "running" || liveGate.status === "error") {
    return false
  }
  const name = skillSlotKey(skill)
  const runSkill = runSkillName(liveGate)
  if (runSkill && runSkill !== name) {
    return false
  }
  if (liveGate.gate_decision !== "cleared") {
    return false
  }
  if (mode === "local") {
    return true
  }
  return isLiveHarness(liveGate.report?.harness || liveGate.harness)
}

export function tryoutMatchesCheck(
  tryout: RunRecord | null | undefined,
  check: Pick<Check, "id" | "prompt">
): boolean {
  if (!tryout || !isTryoutRun(tryout)) {
    return false
  }
  const tasks = tryout.report?.tasks ?? []
  const checkId = (check.id || "").trim()
  if (checkId && tasks.some((task) => task.id === checkId)) {
    return true
  }
  const prompt = (check.prompt || "").trim()
  return Boolean(prompt && tasks.some((task) => (task.prompt || "").trim() === prompt))
}

/** Prefer the in-flight/finished try-out for that one check; Gate SoR stays the full run. */
export function runForCheck(
  check: Pick<Check, "id" | "prompt">,
  gate: RunRecord | null | undefined,
  tryout: RunRecord | null | undefined
): RunRecord | null {
  if (tryoutMatchesCheck(tryout, check)) {
    return tryout ?? null
  }
  return gate && !isTryoutRun(gate) ? gate : null
}

export function patchSkillSlot(
  slots: Record<string, SkillRunSlot>,
  key: string,
  patch: (slot: SkillRunSlot) => SkillRunSlot
): Record<string, SkillRunSlot> {
  const name = key.trim()
  if (!name) {
    return slots
  }
  return {
    ...slots,
    [name]: patch(slots[name] ?? emptySkillRunSlot()),
  }
}
