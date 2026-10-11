import { deployLabel } from "@/lib/dashboard-helpers"
import {
  harnessDisplayName,
  isLegacyRunCopy,
  OLDER_RUN_LABEL,
} from "@/lib/eval-config"
import type { TimelineItem } from "@/lib/types"

export function historyMeta(
  item: TimelineItem & {
    semver?: string
    hash?: string
    harness?: string
  }
) {
  if (item.kind !== "run") {
    return {
      skill: item.skill || item.label || "Deploy",
      version: "",
      config: item.target
        ? `Install to ${deployLabel(item.target) ?? item.target}`
        : item.label || "—",
      fingerprint: "",
    }
  }
  const skill = item.skill || "—"
  const version = item.semver ? `v${item.semver}` : ""
  const rawConfig =
    item.config_label ||
    harnessDisplayName(item.harness || "", item.harness || "") ||
    "—"
  const config = isLegacyRunCopy(rawConfig, item.harness)
    ? OLDER_RUN_LABEL
    : rawConfig
  const fingerprint = item.config_fingerprint || item.hash || ""
  return { skill, version, config, fingerprint }
}
