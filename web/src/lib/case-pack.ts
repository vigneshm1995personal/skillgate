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

export function expectedFieldValue(
  check: Pick<Check, "contains" | "golden_path">
): string {
  const contains = check.contains ?? ""
  if (contains.trim()) {
    return contains
  }
  const golden = (check.golden_path || "").trim()
  if (!golden) {
    return contains
  }
  const base =
    golden.replace(/\\/g, "/").split("/").filter(Boolean).pop() || golden
  return `Matches file ${base}`
}
