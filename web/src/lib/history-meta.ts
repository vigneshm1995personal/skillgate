import { customerScoredBy } from "@/lib/check-results"
import { deployLabel } from "@/lib/dashboard-helpers"
import {
  customerConfigLabel,
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
      configRaw: "",
      fingerprint: "",
    }
  }
  const skill = item.skill || "—"
  const version = item.semver ? `v${item.semver}` : ""
  const stamped =
    item.config_label ||
    harnessDisplayName(item.harness || "", item.harness || "") ||
    "—"
  const rawConfig = item.config_label_raw || stamped
  const config = isLegacyRunCopy(stamped, item.harness)
    ? OLDER_RUN_LABEL
    : looksCustomerConfig(stamped)
      ? stamped
      : customerConfigLabel({ label: rawConfig, harness: item.harness }, item.harness) ||
        customerScoredBy(rawConfig) ||
        rawConfig
  const fingerprint = item.config_fingerprint || item.hash || ""
  return { skill, version, config, configRaw: rawConfig === "—" ? "" : rawConfig, fingerprint }
}

function looksCustomerConfig(text: string): boolean {
  return (
    /scored by /i.test(text) &&
    !/via gateway/i.test(text) &&
    !/openai\//i.test(text)
  )
}
