import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

import { gateTone, stageTitle, stampBadgeProps } from "@/components/dashboard/chrome"

const dir = dirname(fileURLToPath(import.meta.url))

describe("stampBadgeProps", () => {
  it("shows a passing run as Ready, not Blocked", () => {
    const props = stampBadgeProps("pass")
    expect(props.passed).toBe(true)
    expect(gateTone(props.gate, props.passed)).toBe("green")
    expect(gateTone("blocked", false)).toBe("red")
  })
})

describe("stageTitle", () => {
  it("calls the skills list Skills, not Skill Repository", () => {
    expect(stageTitle("repository")).toBe("Skills")
  })
})

describe("sidebar header", () => {
  it("keeps Skill Gate text without the logo mark", () => {
    const sidebar = readFileSync(join(dir, "app-sidebar.tsx"), "utf8")
    expect(sidebar).toMatch(/Skill Gate/)
    expect(sidebar).toMatch(/Eval · Gate · Deploy/)
    expect(sidebar).not.toMatch(/skill-gate-mark/)
  })
})

describe("black and white status", () => {
  it("keeps the Blocked badge monochrome", () => {
    const chrome = readFileSync(join(dir, "chrome.tsx"), "utf8")
    const badge = chrome.slice(
      chrome.indexOf("export function GateBadge"),
      chrome.indexOf("export function SectionLabel")
    )
    expect(badge).toMatch(/Blocked/)
    expect(badge).not.toMatch(/variant="destructive"/)
  })

  it("keeps missing-key and deploy Blocked banners monochrome", () => {
    const evalPage = readFileSync(join(dir, "eval-page.tsx"), "utf8")
    const deploy = readFileSync(join(dir, "deploy-page.tsx"), "utf8")
    const missing = evalPage.slice(
      evalPage.indexOf('id="missing-key"'),
      evalPage.indexOf('id="missing-key-hint"')
    )
    expect(missing).not.toMatch(/variant="destructive"/)
    expect(deploy).toMatch(/id="deploy-note"/)
    expect(deploy).not.toMatch(
      /id="deploy-note"[\s\S]{0,80}variant=\{deployAllowed \? "default" : "destructive"\}/
    )
  })
})
