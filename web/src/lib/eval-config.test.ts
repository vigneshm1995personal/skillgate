import { describe, expect, it } from "vitest"

import {
  MODEL_CUSTOM_VALUE,
  MODEL_DEFAULT_VALUE,
  configLabel,
  customerConfigLabel,
  customerRunDetails,
  friendlyModelName,
  stampRunConfig,
  emptyCatalogHint,
  unsupportedModelHint,
  draftConfigSummary,
  harnessDisplayName,
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
    expect(empty[0]?.label).toBe("Agent default")
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

describe("unsupportedModelHint", () => {
  it("uses plain words instead of gateway model ids", () => {
    const short = unsupportedModelHint("codex", "codex", [])
    const listed = unsupportedModelHint("codex", "codex", ["gpt-5.6-luna"])
    expect(short).toMatch(/Codex model/)
    expect(short).not.toMatch(/gateway ids/i)
    expect(short).not.toMatch(/openai\/gpt-4o-mini/)
    expect(listed).toContain("gpt-5.6-luna")
    expect(listed).not.toMatch(/openai\/gpt-4o-mini/)
    expect(listed).not.toMatch(/gateway model id/i)
    expect(listed).toMatch(/not a Codex model/i)
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

  it("renders leftover skip-judge labels as an older run", () => {
    expect(
      configLabel({
        label: "Built-in checker · 300s",
        harness: "skip",
        timeout_effective: 300,
      })
    ).toBe("Older run (before live-only checks)")
    expect(configLabel({ harness: "demo", timeout_effective: 300 })).toBe(
      "Older run (before live-only checks)"
    )
  })

  it("does not alias a removed demo harness to Auto", () => {
    expect(harnessDisplayName("demo")).not.toBe("Auto")
    expect(configLabel({ harness: "demo" })).not.toBe("Auto")
  })

  it("shows Auto on a fresh project, not Auto · Cursor", () => {
    expect(harnessDisplayName("auto")).toBe("Auto")
    expect(harnessDisplayName("auto", "auto")).toBe("Auto")
    expect(harnessDisplayName("auto", "")).toBe("Auto")
    expect(draftConfigSummary("auto", { model: "", timeoutSec: "" })).toBe("Auto")
    expect(harnessDisplayName("auto", "llm")).toBe("Auto · LLM")
  })

  it("shows the actual LLM model via gateway, not Auto · Cursor", () => {
    expect(
      configLabel({
        harness: "llm",
        harness_pref: "auto",
        model: "openai/gpt-4o-mini",
        applied: { via_gateway: true },
        label: "Auto · Cursor",
      })
    ).toBe("LLM · GPT-4o mini")
  })

  it("hides the default task model unless the user picked it", () => {
    expect(friendlyModelName("openai/gpt-4o-mini")).toBe("GPT-4o mini")
    expect(friendlyModelName("gpt-4o-mini")).toBe("GPT-4o mini")
    expect(
      customerConfigLabel({
        label: "Scored by the judge",
        harness: "llm",
      })
    ).toBe("Scored by the judge")
  })

  it("shows Scored by the judge on History and skill Runs, not the provider", () => {
    expect(
      customerConfigLabel({
        harness: "llm",
        model: "openai/gpt-4o-mini",
        timeout_effective: 300,
        applied: { via_gateway: true },
        label:
          "LLM · openai/gpt-4o-mini via gateway · 300s · OpenAI Decisions via Vercel AI Gateway (your key)",
        judge: {
          provider: "openai",
          display_name:
            "OpenAI Decisions via Vercel AI Gateway (your key)",
        },
      })
    ).toBe("Scored by the judge")
    expect(
      customerConfigLabel({
        harness: "llm",
        model: "gpt-4o-mini",
        applied: { model: true },
        judge: {
          provider: "openai",
          display_name: "OpenAI (your key)",
        },
      })
    ).toBe("Scored by the judge")
  })

  it("puts a user-picked model in Run details only", () => {
    expect(
      customerRunDetails({
        harness: "llm",
        model: "openai/gpt-4o-mini",
        timeout_effective: 300,
        applied: { via_gateway: true },
        judge: {
          provider: "openai",
          display_name: "OpenAI Decisions via Vercel AI Gateway (your key)",
        },
      })
    ).toBe("LLM · 300s")
    expect(
      customerRunDetails({
        harness: "llm",
        model: "gpt-4.1",
        timeout_effective: 300,
        applied: { model: true },
        judge: {
          provider: "openai",
          display_name: "OpenAI (your key)",
        },
      })
    ).toBe("LLM · GPT-4.1 · 300s")
  })

  it("names a chosen scoring provider on History", () => {
    expect(
      customerConfigLabel({
        harness: "llm",
        judge: { provider: "jev", chosen: true, display_name: "Jev" },
      })
    ).toBe("Scored by Jev")
  })

  it("does not treat an openai/ model id as the scorer", () => {
    expect(
      customerConfigLabel({
        harness: "llm",
        model: "openai/gpt-4o-mini",
        applied: { via_gateway: true },
        label: "LLM · openai/gpt-4o-mini via gateway · 300s",
        judge: { provider: "skip", display_name: "Checks" },
      })
    ).toBe("")
  })

  it("prefers the stamped report config over an Auto request", () => {
    expect(
      configLabel(
        stampRunConfig(
          {
            harness: "auto",
            harness_pref: "auto",
            model: "openai/gpt-4o-mini",
            label: "Auto · Cursor",
          },
          {
            harness: "llm",
            model: "openai/gpt-4o-mini",
            applied: { via_gateway: true },
          }
        )
      )
    ).toBe("LLM · GPT-4o mini")
  })
})
