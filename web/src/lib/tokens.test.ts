import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const css = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../index.css"),
  "utf8"
)

describe("design tokens", () => {
  it("does not use the generic purple sidebar accent", () => {
    expect(css).not.toMatch(/264\.376/)
  })

  it("names pass, fail, and warn as first-class colors", () => {
    expect(css).toMatch(/--success:/)
    expect(css).toMatch(/--destructive:/)
    expect(css).toMatch(/--warning:/)
  })

  it("pairs Geist with a display face for the stamp", () => {
    expect(css).toMatch(/--font-display:/)
    expect(css).toMatch(/Newsreader/)
  })
})
