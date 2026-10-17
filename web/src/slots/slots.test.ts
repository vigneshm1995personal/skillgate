import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

import { settingsSurface } from "@/slots/resolve"

const root = join(dirname(fileURLToPath(import.meta.url)), "../..")

describe("shared UI package", () => {
  it("publishes one package cloud can depend on", () => {
    const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8")) as {
      name: string
      exports: Record<string, string>
    }
    expect(pkg.name).toBe("@skillgate/ui")
    expect(pkg.exports["."]).toBe("./src/index.ts")
    expect(pkg.exports["./tokens.css"]).toBe("./src/tokens.css")
    expect(pkg.exports["./styles.css"]).toBe("./src/index.css")
    expect(pkg.exports["./vite"]).toBe("./host/skillgate-ui-plugin.mjs")
    expect(pkg.exports["./slots"]).toBe("./src/slots/index.ts")
  })

  it("keeps hosted tokens in one file, not a second palette", () => {
    const tokens = readFileSync(join(root, "src/tokens.css"), "utf8")
    expect(tokens).toMatch(/--radius:\s*0\.75rem/)
    expect(tokens).toMatch(/--font-heading:\s*var\(--font-sans\)/)
    expect(tokens).toMatch(/color-scheme:\s*light/)
    expect(tokens).toMatch(/color-scheme:\s*dark/)
    expect(tokens).not.toMatch(/sg-page-title/)
    expect(tokens).not.toMatch(/sg-ink-bar/)
    const appCss = readFileSync(join(root, "src/index.css"), "utf8")
    expect(appCss).toMatch(/@import "\.\/tokens\.css"/)
    expect(appCss).not.toMatch(/--radius:/)
  })
})

describe("settingsSurface", () => {
  it("keeps the local agent sign-in screen unless cloud supplies settings", () => {
    expect(settingsSurface("local", true)).toBe("local")
    expect(settingsSurface("cloud", false)).toBe("local")
    expect(settingsSurface("cloud", true)).toBe("hosted")
  })
})

describe("home is the first screen", () => {
  it("opens the dashboard on Home", () => {
    const provider = readFileSync(
      join(root, "src/lib/dashboard-provider.tsx"),
      "utf8"
    )
    expect(provider).toMatch(/useState<Stage>\("home"\)/)
  })
})
