import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

import { switchSaveBody, type DecisionJudge, type JudgeDraft } from "@/lib/judge-setup"

const here = dirname(fileURLToPath(import.meta.url))

const judges: DecisionJudge[] = [
  {
    id: "jev",
    label: "OpenRouter",
    detail: "Uses an OpenRouter key.",
    fields: ["base_url", "model", "key"],
    models: ["typesafe/jev-1.14"],
    defaults: {
      base_url: "https://openrouter.ai/api/v1",
      model: "typesafe/jev-1.14",
    },
    key_name: "JEV_API_KEY",
  },
]

const saved: JudgeDraft = { baseUrl: "", model: "", accountId: "" }

describe("Switch saves the decision model", () => {
  it("builds the same save body as judge provider set", () => {
    expect(switchSaveBody(judges, "jev", "auto", saved)).toMatchObject({
      provider: "jev",
      model: "typesafe/jev-1.14",
      base_url: "https://openrouter.ai/api/v1",
    })
  })

  it("clears the test line on option change and save, and Switch persists", () => {
    const src = readFileSync(join(here, "judge-setup-form.tsx"), "utf8")
    const apply = src.slice(src.indexOf("const applyProvider"), src.indexOf("const persist"))
    const save = src.slice(src.indexOf("const onSave"), src.indexOf("const onTest"))
    expect(apply).toContain('setTestMessage("")')
    expect(save).toContain('setTestMessage("")')
    expect(src).toContain("setSettingsJudge(switchSaveBody")
    expect(src).not.toContain("onSwitch={applyProvider}")
  })
})
