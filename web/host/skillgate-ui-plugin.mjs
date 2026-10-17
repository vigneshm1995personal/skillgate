import { createRequire } from "node:module"
import path from "node:path"

const require = createRequire(import.meta.url)

/** Resolve `@/` inside `@skillgate/ui` to that package's src. */
export function skillgateUiPlugin() {
  let uiSrc = ""
  return {
    name: "skillgate-ui-alias",
    enforce: "pre",
    configResolved() {
      const pkg = require.resolve("@skillgate/ui/package.json")
      uiSrc = path.join(path.dirname(pkg), "src")
    },
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
