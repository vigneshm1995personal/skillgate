import { describe, expect, it } from "vitest"

import {
  MODEL_CUSTOM_VALUE,
  MODEL_DEFAULT_VALUE,
  configLabel,
  emptyCatalogHint,
  knownModelsForHarness,
  modelSelectValue,
  modelsForHarness,
  plainConfigDiff,
  resolveModelHarness,
} from "./eval-config"

describe("resolveModelHarness", () => {
  it("treats explicit claude as a catalog key", () => {
    expect(resolveModelHarness("claude")).toBe("claude")
    expect(resolveModelHarness("claude", "cursor-agent")).toBe("claude")
  })

  it("uses Auto's resolved harness, including claude and llm", () => {
    expect(resolveModelHarness("auto", "codex")).toBe("codex")
    expect(resolveModelHarness("auto", "cursor-agent")).toBe("cursor-agent")
    expect(resolveModelHarness("auto", "claude")).toBe("claude")
    expect(resolveModelHarness("auto", "llm")).toBe("llm")
    expect(resolveModelHarness("auto")).toBe("auto")
  })
})

describe("knownModelsForHarness", () => {
  const catalog = {
    "cursor-agent": ["composer-2.5", "claude-4-sonnet-thinking"],
    codex: ["gpt-5.6-luna"],
    claude: ["claude-sonnet-4-20250514"],
    llm: ["openai/gpt-4o-mini"],
  }

  it("does not union catalogs for Auto", () => {
    expect(knownModelsForHarness("auto", "cursor-agent", catalog)).toEqual([
      "composer-2.5",
      "claude-4-sonnet-thinking",
    ])
    expect(knownModelsForHarness("auto", "codex", catalog)).toEqual(["gpt-5.6-luna"])
    expect(knownModelsForHarness("auto", "cursor-agent", catalog)).not.toContain(
      "gpt-5.6-luna"
    )
  })

  it("shows Claude's discovered list when Claude is selected", () => {
    expect(knownModelsForHarness("claude", "claude", { claude: ["x"] })).toEqual([
      "x",
    ])
  })

  it("returns empty when the catalog is missing or empty (no static fill)", () => {
    expect(knownModelsForHarness("cursor-agent", "cursor-agent", null)).toEqual([])
    expect(knownModelsForHarness("auto", "cursor-agent", {})).toEqual([])
    expect(
      knownModelsForHarness("cursor-agent", "cursor-agent", { "cursor-agent": [] })
    ).toEqual([])
  })
})

describe("modelsForHarness", () => {
  it("always includes Default and Custom…", () => {
    const empty = modelsForHarness("cursor-agent", "cursor-agent", null)
    expect(empty.map((item) => item.value)).toEqual([
      MODEL_DEFAULT_VALUE,
      MODEL_CUSTOM_VALUE,
    ])
    const listed = modelsForHarness("codex", "codex", { codex: ["gpt-5.6-luna"] })
    expect(listed[0]?.value).toBe(MODEL_DEFAULT_VALUE)
    expect(listed.at(-1)?.value).toBe(MODEL_CUSTOM_VALUE)
    expect(listed.map((item) => item.value)).toContain("gpt-5.6-luna")
  })
})

describe("modelSelectValue", () => {
  it("maps unknown ids to Custom…", () => {
    const options = modelsForHarness("codex", "codex", { codex: ["gpt-5.6-luna"] })
    expect(modelSelectValue("", options)).toBe(MODEL_DEFAULT_VALUE)
    expect(modelSelectValue("gpt-5.6-luna", options)).toBe("gpt-5.6-luna")
    expect(modelSelectValue("openai/gpt-4o-mini", options)).toBe(MODEL_CUSTOM_VALUE)
  })
})

describe("emptyCatalogHint", () => {
  it("explains no key vs list failure", () => {
    expect(emptyCatalogHint("cursor-agent", "cursor-agent", null)).toBeNull()
    expect(
      emptyCatalogHint("cursor-agent", "cursor-agent", {
        "cursor-agent": { source: "empty", error: "no_key" },
      })
    ).toMatch(/Settings/)
    expect(
      emptyCatalogHint("cursor-agent", "cursor-agent", {
        "cursor-agent": { source: "empty", error: "list_failed" },
      })
    ).toMatch(/Could not list/)
  })

  it("does not add a second no-key message on Auto", () => {
    expect(
      emptyCatalogHint("auto", "cursor-agent", {
        "cursor-agent": { source: "empty", error: "no_key" },
      })
    ).toBeNull()
    expect(
      emptyCatalogHint("auto", "llm", {
        llm: { source: "empty", error: "list_failed" },
      })
    ).toMatch(/Could not list/)
  })
})

describe("plainConfigDiff", () => {
  it("rewrites timeout_sec: — → 300 into a sentence", () => {
    expect(
      plainConfigDiff([{ field: "timeout_sec", from: null, to: 300 }])
    ).toBe("Time limit is now 5 minutes.")
  })
})

describe("configLabel", () => {
  it("collapses a stored Cursor · 300s · 300s label", () => {
    expect(configLabel({ label: "Cursor · 300s · 300s" })).toBe("Cursor · 300s")
    expect(configLabel({ label: "cursor-agent · 300s · 300s" })).toBe(
      "Cursor · 300s"
    )
  })

  it("names the built-in checker instead of demo", () => {
    expect(configLabel({ harness: "demo" })).toBe("Built-in checker")
    expect(configLabel({ harness: "eval" })).toBe("Built-in checker")
  })
})
