import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const dir = dirname(fileURLToPath(import.meta.url))
const tokensCss = readFileSync(join(dir, "../tokens.css"), "utf8")
const indexCss = readFileSync(join(dir, "../index.css"), "utf8")
const css = `${tokensCss}\n${indexCss}`
const mosaic = readFileSync(
  join(dir, "../components/dashboard/eval-mosaic.tsx"),
  "utf8"
)
const landing = readFileSync(
  join(dir, "../components/marketing/landing-page.module.css"),
  "utf8"
)

const STATUS = new Set(["success", "success-foreground", "destructive"])

function slice(start: string, end?: string) {
  const i = css.indexOf(start)
  const rest = css.slice(i)
  if (!end) return rest
  const j = rest.indexOf(end)
  return j === -1 ? rest : rest.slice(0, j)
}

function parseOklch(value: string) {
  const m = value.match(
    /oklch\(\s*([\d.]+)\s+([\d.]+)(?:\s+([\d.]+))?(?:\s*\/\s*[\d.%]+)?\s*\)/
  )
  if (!m) return null
  return { l: Number(m[1]), c: Number(m[2]), h: m[3] ? Number(m[3]) : 0 }
}

function tokens(block: string) {
  const map = new Map<string, string>()
  for (const match of block.matchAll(/--([a-z0-9-]+):\s*([^;]+);/g)) {
    map.set(match[1], match[2].trim())
  }
  return map
}

const root = tokens(slice(":root {", "\n.dark {"))
const dark = tokens(slice("\n.dark {", "\n}"))

describe("design tokens", () => {
  it("does not use the generic purple sidebar accent", () => {
    expect(css).not.toMatch(/264\.376/)
    expect(css).toMatch(/--radius:\s*0\.75rem/)
  })

  it("names pass, fail, and warn as first-class colors", () => {
    expect(css).toMatch(/--success:/)
    expect(css).toMatch(/--destructive:/)
    expect(css).toMatch(/--warning:/)
  })

  it("uses the hosted success green and a neutral warning", () => {
    expect(root.get("success")).toMatch(/oklch\(0\.55 0\.14 155\)/)
    expect(root.get("warning")).toMatch(/oklch\(0\.50 0 0\)/)
    expect(parseOklch(root.get("warning") ?? "")?.c).toBe(0)
  })

  it("uses Geist as the display face, not a serif", () => {
    expect(css).toMatch(/--font-display:/)
    expect(css).toMatch(/Geist Variable/)
    expect(css).not.toMatch(/Newsreader/)
    expect(css).not.toMatch(/@fontsource-variable\/newsreader/)
  })

  it("gives placeholders and muted copy a dedicated AA color", () => {
    expect(css).toMatch(/--placeholder:/)
    expect(root.get("placeholder")).toMatch(/oklch\(0\.50 0 0\)/)
    expect(dark.get("placeholder")).toMatch(/oklch\(0\.708 0 0\)/)
    const muted = parseOklch(root.get("muted-foreground") ?? "")
    expect(muted?.l).toBe(0.5)
    expect(muted?.c).toBe(0)
  })

  it("does not use low-contrast 60% ink for inactive tabs", () => {
    const tabs = readFileSync(
      join(dir, "../components/ui/tabs.tsx"),
      "utf8"
    )
    expect(tabs).not.toMatch(/text-foreground\/60/)
    expect(tabs).toMatch(/text-muted-foreground/)
  })

  it("is white on near-black in light and black on white in dark", () => {
    const bg = parseOklch(root.get("background") ?? "")
    const fg = parseOklch(root.get("foreground") ?? "")
    const dbg = parseOklch(dark.get("background") ?? "")
    const dfg = parseOklch(dark.get("foreground") ?? "")
    expect(bg).toEqual({ l: 1, c: 0, h: 0 })
    expect(fg?.l).toBe(0.13)
    expect(fg?.c).toBe(0)
    expect(dbg?.l).toBe(0.145)
    expect(dbg?.c).toBe(0)
    expect(dfg?.l).toBe(0.985)
    expect(dfg?.c).toBe(0)
  })

  it("makes primary buttons black in light and white in dark", () => {
    const p = parseOklch(root.get("primary") ?? "")
    const dp = parseOklch(dark.get("primary") ?? "")
    expect(p?.l).toBe(0.13)
    expect(p?.c).toBe(0)
    expect(dp?.l).toBe(0.922)
    expect(dp?.c).toBe(0)
  })

  it("keeps the sidebar neutral, matching the page", () => {
    expect(parseOklch(root.get("sidebar") ?? "")?.c).toBe(0)
    expect(parseOklch(dark.get("sidebar") ?? "")?.c).toBe(0)
    expect(parseOklch(root.get("sidebar") ?? "")?.l).toBe(0.985)
    expect(parseOklch(dark.get("sidebar") ?? "")?.l).toBe(0.205)
  })

  it("uses chroma only for pass green and fail red", () => {
    for (const [name, value] of root) {
      const parsed = parseOklch(value)
      if (!parsed || STATUS.has(name)) continue
      expect({ name, c: parsed.c }, `${name} should be gray`).toEqual({
        name,
        c: 0,
      })
    }
    for (const [name, value] of dark) {
      const parsed = parseOklch(value)
      if (!parsed || STATUS.has(name)) continue
      expect({ name, c: parsed.c }, `${name} should be gray`).toEqual({
        name,
        c: 0,
      })
    }
    expect(parseOklch(root.get("success") ?? "")?.c).toBeGreaterThan(0)
    expect(parseOklch(root.get("destructive") ?? "")?.c).toBeGreaterThan(0)
  })

  it("does not fade disabled buttons into gray-on-gray", () => {
    const button = readFileSync(join(dir, "../components/ui/button.tsx"), "utf8")
    expect(button).not.toMatch(/disabled:opacity-50/)
    expect(button).toMatch(/disabled:text-foreground/)
    expect(button).not.toMatch(/disabled:text-foreground\/90/)
    expect(button).not.toMatch(/disabled:bg-foreground\/20/)
    expect(button).toMatch(/ghost:[\s\S]*disabled:bg-transparent/)
  })

  it("does not wash sidebar skill-card copy with low-contrast /70", () => {
    const sidebar = readFileSync(
      join(dir, "../components/dashboard/app-sidebar.tsx"),
      "utf8"
    )
    expect(sidebar).not.toMatch(/sidebar-foreground\/70/)
  })
})

describe("status color is marks and badges only", () => {
  it("paints the heatmap in grayscale", () => {
    expect(mosaic).not.toMatch(/bg-success/)
    expect(mosaic).not.toMatch(/bg-destructive/)
    expect(mosaic).toMatch(/bg-foreground/)
    expect(mosaic).toMatch(/gray means no evals/)
  })

  it("fills the checking bar with ink, not pass green", () => {
    expect(css).toMatch(
      /\.eval-check-progress > i \{[\s\S]*?background: var\(--foreground\)/
    )
  })
})

describe("landing palette", () => {
  it("is black and white, not cream or espresso", () => {
    expect(landing).toMatch(/--sg-bg:\s*#000/)
    expect(landing).toMatch(/--sg-text:\s*#fff/)
    expect(landing).not.toMatch(/#2a1c16/)
    expect(landing).not.toMatch(/#faedd6/)
    expect(landing).not.toMatch(/font-family: var\(--font-display\), serif/)
  })
})
