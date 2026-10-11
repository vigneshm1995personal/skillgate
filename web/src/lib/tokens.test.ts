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

  it("keeps light-mode warning as dark as success so chip text meets AA", () => {
    const root = css.slice(css.indexOf(":root {"), css.indexOf("\n.dark {"))
    expect(root).toMatch(/--success:\s*oklch\(0\.[34]/)
    expect(root).toMatch(/--warning:\s*oklch\(0\.[34]/)
    expect(root).not.toMatch(/--warning:\s*oklch\(0\.72/)
  })

  it("pairs Geist with a display face for the stamp", () => {
    expect(css).toMatch(/--font-display:/)
    expect(css).toMatch(/Newsreader/)
  })

  it("gives placeholders and muted copy a dedicated AA color", () => {
    expect(css).toMatch(/--placeholder:/)
    const root = css.slice(css.indexOf(":root {"), css.indexOf("\n.dark {"))
    const dark = css.slice(css.indexOf("\n.dark {"))
    expect(root).toMatch(/--placeholder:\s*oklch\(0\.[34]/)
    expect(dark).toMatch(/--placeholder:\s*oklch\(0\.[789]/)
    expect(root).not.toMatch(/--primary:\s*oklch\(0\.22/)
  })

  it("does not fade disabled buttons into gray-on-gray", () => {
    const button = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../components/ui/button.tsx"),
      "utf8"
    )
    expect(button).not.toMatch(/disabled:opacity-50/)
    expect(button).toMatch(/disabled:text-foreground\/90/)
    expect(button).toMatch(/disabled:bg-foreground\/20/)
    expect(button).toMatch(/ghost:[\s\S]*disabled:bg-transparent/)
  })
})
