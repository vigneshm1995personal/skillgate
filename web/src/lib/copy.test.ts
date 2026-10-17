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
  "Config changed",
  "Start Evaluations",
  "pack hash",
  "semver + pack hash",
  "built-in checker",
  "This is not a live model",
  "Full runs decide the gate",
  "not the live Deploy gate",
  "Pass the checks to unlock Install.",
  "unlock Install",
  "sets Install",
  "Install still follows",
  "doesn't change Install",
  "OpenAI was unsure",
  "Scored by OpenAI",
  "OpenAI Decisions",
  "via Vercel AI Gateway",
  "gpt-6-luna",
  "Gate pre-selected skill",
  "skip catalog discovery",
  "Decisions",
  "Bedrock",
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
    expect(app).toMatch(/id=["']main["'][\s\S]{0,120}tabIndex=\{-1\}/)
  })
})

describe("skill run rows", () => {
  it("opens a run from the keyboard, not only a click", () => {
    const src = readFileSync(
      join(componentsRoot, "dashboard/skill-detail-page.tsx"),
      "utf8"
    )
    expect(src).toMatch(/tabIndex=\{run\.id \? 0/)
    expect(src).toMatch(/onKeyDown/)
    expect(src).toMatch(/event\.key !== "Enter"/)
  })
})

describe("settings footer", () => {
  it("shows the package version and a build id for QA", () => {
    const src = readFileSync(
      join(componentsRoot, "dashboard/settings-page.tsx"),
      "utf8"
    )
    expect(src).toMatch(/status\?\.version/)
    expect(src).toMatch(/status\?\.build/)
  })

  it("shows agent sign-in and an optional judge key, not provider key fields", () => {
    const src = readFileSync(
      join(componentsRoot, "dashboard/settings-page.tsx"),
      "utf8"
    )
    expect(src).toMatch(/signed in/)
    expect(src).toMatch(/not signed in/)
    expect(src).toMatch(/Judge key \(optional\)/)
    expect(src).toMatch(/Skip it to run without the judge/)
    expect(src).toMatch(/api\.loginStatus/)
    expect(src).toMatch(/api\.startLogin/)
    expect(src).toMatch(/Sign in/)
    expect(src.match(/type="password"/g) ?? []).toHaveLength(1)
    expect(src).not.toMatch(/Model keys/)
    expect(src).not.toMatch(/Keys stay on this machine/)
    expect(src).not.toMatch(/Runs live checks/)
    expect(src).not.toMatch(/Paste key/)
    expect(src).not.toMatch(/Claude \/ Anthropic/)
    expect(src).not.toMatch(/settings-cursor-input/)
    expect(src).not.toMatch(/settings-codex-input/)
    expect(src).not.toMatch(/settings-openai-input/)
    expect(src).not.toMatch(/settings-anthropic-input/)
    expect(src).not.toMatch(/CURSOR_API_KEY/)
    expect(src).not.toMatch(/CODEX_API_KEY/)
    expect(src).not.toMatch(/ANTHROPIC_API_KEY/)
    expect(src).not.toMatch(/label: "OpenAI"/)
    expect(src).not.toMatch(/label: "Anthropic"/)
    expect(src).not.toMatch(/label: "Jev"/)
    expect(src).not.toMatch(/AI Gateway/)
    expect(src).not.toMatch(/Scoring provider/)
    expect(src).not.toMatch(/Decisions/)
    expect(src).not.toMatch(/Bedrock/)
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

  it("hides run plumbing behind Run details", () => {
    const src = readFileSync(
      join(componentsRoot, "dashboard/eval-stamp-body.tsx"),
      "utf8"
    )
    expect(src).toMatch(/Run details/)
    expect(src).toMatch(/Get a passing run to unlock Deploy\./)
  })
})
