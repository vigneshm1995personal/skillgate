import { describe, expect, it } from "vitest"

import { isSameSkill, matchesSkill } from "./dashboard-helpers"

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
