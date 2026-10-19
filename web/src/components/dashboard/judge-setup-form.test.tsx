import { renderToStaticMarkup } from "react-dom/server"
import { describe, expect, it } from "vitest"

import { JudgeSetupForm } from "@/components/dashboard/judge-setup-form"
import {
  judgeSaveBody,
  mismatchCopy,
  type DecisionJudge,
  type JudgeDraft,
} from "@/lib/judge-setup"

const judges: DecisionJudge[] = [
  {
    id: "openai",
    label: "OpenAI",
    detail: "Uses an OpenAI key.",
    fields: ["key"],
    key_name: "OPENAI_API_KEY",
    key_label: "API key",
  },
  {
    id: "jev",
    label: "OpenRouter",
    detail: "Uses an OpenRouter key.",
    fields: ["base_url", "model", "key"],
    advanced: ["base_url", "model"],
    models: ["typesafe/jev-1.14"],
    defaults: {
      base_url: "https://openrouter.ai/api/v1",
      model: "typesafe/jev-1.14",
    },
    key_name: "JEV_API_KEY",
    key_label: "API key",
  },
  {
    id: "clef",
    label: "Cloudflare",
    detail: "Uses a Cloudflare token.",
    fields: ["account_id", "model", "key"],
    models: ["clef", "clef-flash"],
    defaults: { model: "clef" },
    key_name: "CLOUDFLARE_API_TOKEN",
    key_label: "Token",
  },
  {
    id: "custom",
    label: "Custom endpoint",
    detail: "Uses a key for this URL.",
    fields: ["base_url", "model", "key"],
    model_free: true,
    key_name: "CUSTOM_DECISION_API_KEY",
    key_label: "API key",
  },
]

const empty: JudgeDraft = { baseUrl: "", model: "", accountId: "" }

function markup(
  provider: string,
  draft: JudgeDraft = empty,
  extra: {
    testMessage?: string
    testOk?: boolean
    switchTo?: string
    showKey?: boolean
  } = {}
) {
  const option = judges.find((row) => row.id === provider)
  return renderToStaticMarkup(
    <JudgeSetupForm
      idPrefix="settings-judge"
      judges={judges}
      provider={provider}
      onProvider={() => undefined}
      draft={draft}
      onDraft={() => undefined}
      keyDraft=""
      onKeyDraft={() => undefined}
      keyLabel={option?.key_label || "API key"}
      keySet={false}
      showKey={extra.showKey ?? Boolean(option?.key_name)}
      testMessage={extra.testMessage}
      testOk={extra.testOk}
      switchTo={extra.switchTo}
      onSwitch={() => undefined}
      onSave={() => undefined}
      onTest={() => undefined}
      onClear={() => undefined}
      clearHint="Clear the saved key"
    />
  )
}

function has(html: string, id: string): boolean {
  return html.includes(`id="${id}"`)
}

describe("decision model fields", () => {
  it("shows only the key for OpenAI", () => {
    const html = markup("openai")
    expect(has(html, "settings-judge-key-input")).toBe(true)
    expect(html).toContain("Uses an OpenAI key.")
    expect(has(html, "settings-judge-base-url")).toBe(false)
    expect(has(html, "settings-judge-model")).toBe(false)
    expect(has(html, "settings-judge-account-id")).toBe(false)
    expect(html).not.toContain("<details")
    expect(html.match(/type="password"/g) ?? []).toHaveLength(1)
  })

  it("shows the OpenRouter URL, model list, and key", () => {
    const html = markup("jev", {
      baseUrl: "https://openrouter.ai/api/v1",
      model: "typesafe/jev-1.14",
      accountId: "",
    })
    expect(html).toContain("<details open")
    expect(html).toContain("Advanced")
    expect(has(html, "settings-judge-base-url")).toBe(true)
    expect(has(html, "settings-judge-model")).toBe(true)
    expect(has(html, "settings-judge-key-input")).toBe(true)
    expect(html).toContain("typesafe/jev-1.14")
    expect(html).toContain("https://openrouter.ai/api/v1")
    expect(has(html, "settings-judge-account-id")).toBe(false)
    expect(html).toContain("Uses an OpenRouter key.")
  })

  it("shows the account id, model list, and token", () => {
    const html = markup("clef", { baseUrl: "", model: "clef", accountId: "abc123" })
    expect(has(html, "settings-judge-account-id")).toBe(true)
    expect(has(html, "settings-judge-model")).toBe(true)
    expect(has(html, "settings-judge-key-input")).toBe(true)
    expect(html).toContain(">Token<")
    expect(html).toContain('value="clef"')
    expect(html).toContain('value="clef-flash"')
    expect(has(html, "settings-judge-base-url")).toBe(false)
    expect(html).not.toContain("<details")
  })

  it("shows a free-text model for a custom endpoint", () => {
    const html = markup("custom", {
      baseUrl: "https://example.com/v1",
      model: "demo",
      accountId: "",
    })
    expect(has(html, "settings-judge-base-url")).toBe(true)
    expect(has(html, "settings-judge-model")).toBe(true)
    expect(has(html, "settings-judge-key-input")).toBe(true)
    expect(has(html, "settings-judge-account-id")).toBe(false)
    expect(html.match(/<select/g) ?? []).toHaveLength(1)
    expect(html).not.toContain("clef-flash")
  })

  it("paints a pass green and a failure red, and offers a switch", () => {
    const pass = markup("openai", empty, {
      testMessage: "This decision model works.",
      testOk: true,
    })
    expect(pass).toContain('id="settings-judge-test" class="text-sm text-success"')
    expect(pass).toContain('id="btn-settings-test-judge"')
    const fail = markup("openai", empty, {
      testMessage: "This API key was rejected.",
      testOk: false,
      switchTo: "jev",
    })
    expect(fail).toContain('id="settings-judge-test" class="text-sm text-destructive"')
    expect(fail).not.toContain('id="settings-judge-test" class="text-sm text-success"')
    expect(fail).toContain("Switch to OpenRouter")
    expect(has(fail, "settings-judge-switch")).toBe(true)
  })
})

describe("save payload", () => {
  it("sends only the fields that option stores", () => {
    const jev = judges[1]
    expect(
      judgeSaveBody(jev, "jev", {
        baseUrl: "https://openrouter.ai/api/v1",
        model: "typesafe/jev-1.14",
        accountId: "should-drop",
      })
    ).toEqual({
      provider: "jev",
      base_url: "https://openrouter.ai/api/v1",
      model: "typesafe/jev-1.14",
      account_id: null,
      region: null,
    })
    expect(
      judgeSaveBody(judges[0], "openai", {
        baseUrl: "https://openrouter.ai/api/v1",
        model: "clef",
        accountId: "abc",
      }).base_url
    ).toBeNull()
  })

  it("names the other option when the key prefix does not match", () => {
    const copy = mismatchCopy("openai", "sk-or-v1-example", judges)
    expect(copy?.switchTo).toBe("jev")
    expect(copy?.message).toContain("OpenRouter")
    expect(copy?.message).toContain("skillgate judge provider set jev")
    expect(mismatchCopy("openai", "sk-live", judges)).toBeNull()
  })
})
