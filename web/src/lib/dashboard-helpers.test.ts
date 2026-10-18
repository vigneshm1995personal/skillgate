import { describe, expect, it } from "vitest"

import {
  collectChecksForRun,
  deployLabel,
  installedNote,
  isSameSkill,
  matchesSkill,
  sidebarVersionLabel,
} from "./dashboard-helpers"
import type { Check } from "./types"

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

describe("collectChecksForRun", () => {
  it("keeps golden files on imported pdf checks so Run can score them", () => {
    const checks: Check[] = [
      {
        id: "merge-alpha-beta",
        prompt: "Merge alpha.pdf and beta.pdf into output/merged.pdf",
        should_trigger: true,
        output_path: "output/merged.pdf",
        contains: null,
        golden_path: "evals/goldens/merge-alpha-beta.pdf",
        golden_kind: "bytes",
        files: [
          { src: "evals/fixtures/alpha.pdf", dest: "alpha.pdf" },
          { src: "evals/fixtures/beta.pdf", dest: "beta.pdf" },
        ],
        min_pages: 2,
      },
      {
        id: "no-trigger-unrelated",
        prompt: "Write a pytest for a FastAPI /health endpoint.",
        should_trigger: false,
        files: [],
      },
    ]
    const payload = collectChecksForRun(checks, {
      id: "pdf",
      name: "pdf",
      slug: "pdf",
      absolute: "/tmp/skills/pdf",
    })
    expect(payload[0].golden_path).toBe("evals/goldens/merge-alpha-beta.pdf")
    expect(payload[0].golden_kind).toBe("bytes")
    expect(payload[0].output_path).toBe("output/merged.pdf")
    expect(payload[0].id).toBe("merge-alpha-beta")
    expect(payload[0].output_optional).toBe(false)
    expect(payload[1].should_trigger).toBe(false)
  })

  it("keeps an optional output flag on the run payload", () => {
    const payload = collectChecksForRun(
      [
        {
          id: "rh-split",
          prompt: "Keep the prompt.",
          should_trigger: true,
          output_path: "changes.diff",
          contains:
            "The agent leaves tests/ unchanged and asks which behavior product wants.",
          output_optional: true,
        },
      ],
      {
        id: "demo",
        name: "demo",
        slug: "demo",
        absolute: "/tmp/skills/demo",
      }
    )
    expect(payload[0].output_optional).toBe(true)
    expect(payload[0].contains).toContain("leaves tests/ unchanged")
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
