import type { Check } from "@/lib/types"

export function isPinnedCheck(check: Check): boolean {
  return check.bank_status === "pinned"
}

export function isCompletionCheck(check: Check): boolean {
  return Boolean(
    check.should_trigger !== false &&
      ((check.output_path || "").trim() || (check.golden_path || "").trim())
  )
}

export function canPinCheck(check: Check): boolean {
  if (check.should_trigger === false) {
    return Boolean((check.prompt || "").trim())
  }
  if ((check.golden_path || "").trim()) {
    return true
  }
  if ((check.contains || "").trim()) {
    return true
  }
  return !isCompletionCheck(check)
}

export function pinnedCaseCount(checks: Check[]): number {
  return checks.filter(isPinnedCheck).length
}
