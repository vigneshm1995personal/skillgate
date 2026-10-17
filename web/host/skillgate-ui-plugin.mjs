import path from "node:path"
import { fileURLToPath } from "node:url"

const uiRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")

/** Resolve `@/` inside `@skillgate/ui` to that package's src. */
export function skillgateUiPlugin() {
  const uiSrc = path.join(uiRoot, "src")
  return {
    name: "skillgate-ui-alias",
    enforce: "pre",
    async resolveId(source, importer) {
      if (!source.startsWith("@/") || !importer || !uiSrc) {
        return null
      }
      const normalized = importer.replaceAll("\\", "/")
      if (!normalized.includes("/node_modules/@skillgate/ui/")) {
        return null
      }
      const target = path.join(uiSrc, source.slice(2))
      return this.resolve(target, importer, { skipSelf: true })
    },
  }
}
