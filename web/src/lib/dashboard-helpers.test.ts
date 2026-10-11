import { describe, expect, it } from "vitest"

import {
  deployLabel,
  installedNote,
  isSameSkill,
  matchesSkill,
  sidebarVersionLabel,
} from "./dashboard-helpers"

const idea = {
  id: "idea-brainstorming",
  slug: "idea-brainstorming",
  name: "Idea brainstorming",
  absolute: "/tmp/skills/idea-brainstorming",
}

describe("matchesSkill / isSameSkill", () => {
  it("uses slug and id, not the display name", () => {
    expect(matchesSkill(idea, "idea-brainstorming")).toBe(true)
    expect(matchesSkill(idea, idea.absolute)).toBe(true)
    expect(matchesSkill(idea, "Idea brainstorming")).toBe(false)
    expect(isSameSkill(idea, "Idea brainstorming")).toBe(false)
    expect(isSameSkill(idea, "idea-brainstorming")).toBe(true)
    expect(
      isSameSkill(idea, idea.absolute, {
        ...idea,
        name: "Idea brainstorming",
      })
    ).toBe(true)
  })
})

describe("sidebarVersionLabel", () => {
  it("renders the package version on first paint when status is known", () => {
    expect(sidebarVersionLabel({ version: "0.4.1" })).toBe("v0.4.1")
    expect(sidebarVersionLabel(null)).toBe("Skill Gate")
    expect(sidebarVersionLabel({})).toBe("Skill Gate")
  })
})

describe("deployLabel / installedNote", () => {
  it("capitalizes install targets", () => {
    expect(deployLabel("cursor")).toBe("Cursor")
    expect(installedNote("pdf", { target: "cursor" })).toBe(
      "Installed pdf to Cursor."
    )
    expect(installedNote("pdf", { semver: "1.0.0", target: "cursor" })).toBe(
      "Installed pdf v1.0.0 to Cursor."
    )
  })
})
