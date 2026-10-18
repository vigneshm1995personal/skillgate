import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const here = dirname(fileURLToPath(import.meta.url))

function source(name: string): string {
  return readFileSync(join(here, name), "utf8")
}

const PROVIDER_NAMES = /OpenAI|Bedrock|Jev|Clef|Anthropic|gpt-|Decisions|aws|compatible/

describe("Checks tab", () => {
  it("orders the sections and keeps one live Run button", () => {
    const page = source("eval-page.tsx")
    const order = [
      "eval-step-agent",
      "eval-step-cases",
      "eval-step-builtins",
      "eval-step-yours",
      "eval-step-judge",
      "btn-run",
      "eval-step-results",
    ]
    const indexes = order.map((id) => page.indexOf(id))
    expect(indexes.every((index) => index >= 0)).toBe(true)
    for (let i = 1; i < indexes.length; i += 1) {
      expect(indexes[i]).toBeGreaterThan(indexes[i - 1])
    }
    expect(page).toMatch(/Agent setup/)
    expect(page).toMatch(/Test cases/)
    expect(page).toMatch(/<CheckList/)
    expect(page).toMatch(/Built-in checks/)
    const cases = source("check-list.tsx")
    expect(cases).toMatch(/Output file is optional/)
    expect(cases).toMatch(/outputOptionalNote/)
    expect(page).toMatch(/Your checks/)
    expect(page).toMatch(/runButtonLabel/)
    expect(page).not.toMatch(/Bring a skill/)
    expect(page).not.toMatch(/Did it finish the task/)
    expect(page).not.toMatch(/Choose for me/)
    expect(page).not.toMatch(PROVIDER_NAMES)
  })

  it("loads judge prompts from the engine", () => {
    const prompts = source("check-prompts.tsx")
    const judge = source("judge-section.tsx")
    expect(prompts).toMatch(/listChecks/)
    expect(prompts).toMatch(/previewCheck/)
    expect(prompts).not.toMatch(/Did it finish the task/)
    expect(prompts).not.toMatch(PROVIDER_NAMES)
    expect(judge).toMatch(/decisionJudges/)
    expect(judge).not.toMatch(PROVIDER_NAMES)
    expect(judge).toMatch(/Not selected/)
    expect(judge).toMatch(/account_id: saved\.account_id/)
  })
})
