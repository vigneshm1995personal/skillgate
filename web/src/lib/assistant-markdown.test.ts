import { describe, expect, it } from "vitest"

import { parseAssistantMarkdown } from "./assistant-markdown"

describe("parseAssistantMarkdown", () => {
  it("renders bold, inline code, fences, and bullets without HTML", () => {
    const blocks = parseAssistantMarkdown(
      [
        "I created `output/status.pdf`. It has a **Q3 Status** heading.",
        "",
        "- **Summary:** billing API shipped",
        "- **Risks:** blocked on design review",
        "",
        "```",
        "ps say to avoid files",
        "```",
      ].join("\n")
    )
    expect(blocks.some((block) => block.type === "ul")).toBe(true)
    expect(blocks.some((block) => block.type === "pre")).toBe(true)
    const para = blocks.find((block) => block.type === "p")
    expect(para && para.type === "p" ? para.children : []).toEqual(
      expect.arrayContaining([
        { type: "code", text: "output/status.pdf" },
        { type: "strong", text: "Q3 Status" },
      ])
    )
    expect(JSON.stringify(blocks)).not.toMatch(/<script|<\/p>/i)
  })
})
