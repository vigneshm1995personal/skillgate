import { createRequire } from "node:module"
import path from "node:path"
import type { Plugin } from "vite"

/**
 * Resolve `@/` inside `@skillgate/ui` to that package's src.
 * The host app keeps its own `@` alias for files outside the package.
 */
export function skillgateUiPlugin(): Plugin {
  const require = createRequire(import.meta.url)
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
