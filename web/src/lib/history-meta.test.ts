import { describe, expect, it } from "vitest"

import { historyMeta } from "./history-meta"

describe("historyMeta", () => {
  it("does not alias a removed demo harness to Auto", () => {
    expect(
      historyMeta({
        kind: "run",
        skill: "pdf",
        harness: "demo",
      }).config
    ).not.toBe("Auto")
  })

  it("capitalizes Install to Cursor", () => {
    expect(
      historyMeta({
        kind: "deploy",
        skill: "pdf",
        target: "cursor",
      }).config
    ).toBe("Install to Cursor")
  })

  it("shows a plain model · scorer line, not gateway plumbing", () => {
    const meta = historyMeta({
      kind: "run",
      skill: "pdf",
      harness: "llm",
      config_label:
        "LLM · openai/gpt-4o-mini via gateway · 300s · OpenAI Decisions via Vercel AI Gateway (your key)",
    })
    expect(meta.config).toBe("GPT-4o mini · Scored by OpenAI Decisions")
    expect(meta.configRaw).toContain("openai/gpt-4o-mini")
    expect(meta.configRaw).toContain("via gateway")
  })

  it("renders leftover skip-judge rows as an older run", () => {
    expect(
      historyMeta({
        kind: "run",
        skill: "pdf",
        harness: "skip",
        config_label: "Skip · 300s",
      }).config
    ).toBe("Older run (before live-only checks)")
    expect(
      historyMeta({
        kind: "run",
        skill: "pdf",
        harness: "llm",
        config_label: "Built-in checker · 300s",
      }).config
    ).toBe("Older run (before live-only checks)")
    expect(
      historyMeta({
        kind: "run",
        skill: "pdf",
        harness: "demo",
        config_label: "Demo · 300s",
      }).config
    ).toBe("Older run (before live-only checks)")
  })
})
