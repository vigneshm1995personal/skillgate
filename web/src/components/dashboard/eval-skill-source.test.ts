import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const here = dirname(fileURLToPath(import.meta.url))

function source(name: string): string {
  return readFileSync(join(here, name), "utf8")
}

describe("Evaluate skill tab", () => {
  it("lists skills already on disk and does not offer paste or zip", () => {
    const page = source("eval-page.tsx")
    expect(page).toMatch(/Pick a skill/)
    expect(page).not.toMatch(/Bring a skill/)
    expect(page).not.toMatch(/btn-paste/)
    expect(page).not.toMatch(/Drop a \.zip/)
    expect(page).not.toMatch(/pasteSkill|uploadZip|PASTE_PLACEHOLDER/)

    const provider = readFileSync(
      join(here, "../../lib/dashboard-provider.tsx"),
      "utf8"
    )
    expect(provider).not.toMatch(/pasteSkill|uploadZip/)
  })
})
