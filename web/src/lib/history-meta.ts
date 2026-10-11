import { configLabel, harnessDisplayName } from "@/lib/eval-config"
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
      config: item.target ? `Install to ${item.target}` : item.label || "—",
      fingerprint: "",
    }
  }
  const skill = item.skill || "—"
  const version = item.semver ? `v${item.semver}` : ""
  const raw =
    item.config_label ||
    item.harness ||
    (item.label || "")
      .replace(/^(GREEN|RED)\s+/i, "")
      .replace(new RegExp(`^${skill}\\s*`), "")
      .replace(/^v[^\s·]+ · /, "")
      .replace(/ · [a-f0-9]{8,}$/i, "")
      .trim() ||
    "—"
  const config =
    item.config_label ||
    (item.harness ? harnessDisplayName(item.harness, item.harness) : "") ||
    configLabel(
      raw && raw !== "—" ? { label: raw, harness: item.harness } : { harness: item.harness }
    ) ||
    harnessDisplayName(raw, raw)
  const fingerprint =
    item.config_fingerprint ||
    item.hash ||
    (item.label || "").match(/([a-f0-9]{8,12})$/i)?.[1] ||
    ""
  return { skill, version, config, fingerprint }
}
