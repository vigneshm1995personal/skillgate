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

  it("shows a needs-review run as REVIEW, not RED", () => {
    const props = stampBadgeProps("review")
    expect(props.passed).toBe(true)
    expect(gateTone(props.gate, props.passed)).toBe("review")
    expect(gateTone("needs review", true)).toBe("review")
    expect(gateTone("needs review", true)).not.toBe("green")
  })
})

describe("stageTitle", () => {
  it("calls the skills list Skill Repository, matching the hosted shell", () => {
    expect(stageTitle("repository")).toBe("Skill Repository")
  })
})

describe("sidebar header", () => {
  it("shows the SG mark beside the Skill Gate wordmark", () => {
    const sidebar = readFileSync(join(dir, "app-sidebar.tsx"), "utf8")
    const mark = readFileSync(join(dir, "../brand/sg-mark.tsx"), "utf8")
    const svg = readFileSync(join(dir, "../../../public/sg-mark.svg"), "utf8")
    expect(sidebar).toMatch(/Skill Gate/)
    expect(sidebar).toMatch(/Evaluate, Gate, Deploy/)
    expect(sidebar).toMatch(/SgMark/)
    expect(sidebar).not.toMatch(/skill-gate-mark/)
    expect(sidebar).not.toMatch(/sg-ink-bar/)
    expect(mark).toContain("M100 0")
    expect(mark).toContain('fill="currentColor"')
    expect(svg).toContain("M100 0")
    expect(svg).toContain("currentColor")
  })
})

describe("hosted gate badge", () => {
  it("uses the hosted GREEN and RED badges", () => {
    const chrome = readFileSync(join(dir, "chrome.tsx"), "utf8")
    const badge = chrome.slice(
      chrome.indexOf("export function GateBadge"),
      chrome.indexOf("export function SectionLabel")
    )
    expect(badge).toMatch(/GREEN/)
    expect(badge).toMatch(/RED/)
    expect(badge).toMatch(/REVIEW/)
    expect(badge).toMatch(/variant="destructive"/)
    expect(badge).toMatch(/variant="warning"/)
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
    expect(deploy).toMatch(
      /id="deploy-note"[\s\S]{0,120}variant=\{deployAllowed \? "default" : "destructive"\}/
    )
  })
})
