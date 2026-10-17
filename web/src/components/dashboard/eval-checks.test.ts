import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const here = dirname(fileURLToPath(import.meta.url))

describe("Evaluate checks tab", () => {
  it("orders the sections and loads judge prompts from the engine", () => {
    const page = readFileSync(join(here, "eval-page.tsx"), "utf8")
    const agent = page.indexOf('id="checks-agent"')
    const cases = page.indexOf('id="checks-cases"')
    const builtin = page.indexOf('id="checks-builtin"')
    const yours = page.indexOf('id="checks-yours"')
    const judge = page.indexOf('id="checks-judge"')
    const run = page.indexOf('id="btn-run"')
    expect(agent).toBeGreaterThan(-1)
    expect(agent).toBeLessThan(cases)
    expect(cases).toBeLessThan(builtin)
    expect(builtin).toBeLessThan(yours)
    expect(yours).toBeLessThan(judge)
    expect(judge).toBeLessThan(run)
    expect(page).toMatch(/runButtonLabel/)
    expect(page).not.toMatch(/Bring a skill/)

    const prompts = readFileSync(join(here, "scoring-questions.tsx"), "utf8")
    expect(prompts).toMatch(/judgeChecks\(\)/)
    expect(prompts).toMatch(/readOnly/)
    expect(prompts).toMatch(/readOnly=\{false\}/)
    expect(prompts).not.toMatch(/The requested work is fully done/)
  })
})
