import type { StatusPayload } from "@/lib/types"

export type ProductMode = "local" | "cloud"

export type FeatureSlot =
  | "signIn"
  | "billing"
  | "sharedHistory"
  | "hostedJudge"
  | "sandboxes"
  | "tryoutCaps"
  | "generateChecks"
  | "gitPublish"
  | "suggestUpdates"
  | "analyticsHome"

/** Hosted surfaces. Hidden in local mode, not locked. */
export type FeatureSlots = Record<FeatureSlot, boolean>

export function productMode(status?: StatusPayload | null): ProductMode {
  return status?.mode === "cloud" ? "cloud" : "local"
}

export function isLocalMode(status?: StatusPayload | null): boolean {
  return productMode(status) === "local"
}

export function slotOn(
  status: StatusPayload | null | undefined,
  name: FeatureSlot
): boolean {
  if (productMode(status) === "local") {
    return Boolean(status?.slots?.[name])
  }
  if (status?.slots) {
    return Boolean(status.slots[name])
  }
  return true
}
