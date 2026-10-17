import type { ProductMode } from "@/lib/mode"

/** Cloud supplies Settings; local always keeps the agent sign-in screen. */
export function settingsSurface(
  mode: ProductMode,
  hostedSettings: boolean
): "local" | "hosted" {
  if (mode === "cloud" && hostedSettings) {
    return "hosted"
  }
  return "local"
}
