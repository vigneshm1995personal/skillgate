import { readdirSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const CUSTOMER_DENY = [
  "Import checks from YAML",
  "Import YAML",
  "Load YAML",
  "Cursor Agent harness",
  "Browse all in Repository",
  "browse all in Repository",
  "Skill Repository",
  "Eval spend",
  "Eval runs",
  "Config changed",
  "Start Evaluations",
  "pack hash",
  "semver + pack hash",
  "built-in checker",
] as const

const componentsRoot = join(dirname(fileURLToPath(import.meta.url)), "../components")

function walkTsx(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const next = join(dir, entry.name)
    if (entry.isDirectory()) {
      out.push(...walkTsx(next))
    } else if (entry.name.endsWith(".tsx")) {
      out.push(next)
    }
  }
  return out
}

describe("skip link", () => {
  it("sends keyboard users to main content", () => {
    const app = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../App.tsx"),
      "utf8"
    )
    expect(app).toMatch(/href=["']#main["']/)
    expect(app).toMatch(/id=["']main["']/)
  })
})

describe("customer copy", () => {
  it("does not show internal lingo in components", () => {
    const hits: string[] = []
    for (const file of walkTsx(componentsRoot)) {
      const text = readFileSync(file, "utf8")
      for (const phrase of CUSTOMER_DENY) {
        if (text.includes(phrase)) {
          hits.push(`${file.slice(componentsRoot.length + 1)}: ${phrase}`)
        }
      }
    }
    expect(hits).toEqual([])
  })
})
