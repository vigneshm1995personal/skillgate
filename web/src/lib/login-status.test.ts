import { describe, expect, it } from "vitest"

import { agentSessionLabel } from "./login-status"

describe("agentSessionLabel", () => {
  it("maps subscription login and leftover keys to signed in", () => {
    expect(agentSessionLabel({ auth: "cli_login", status: "logged in" })).toBe(
      "signed in"
    )
    expect(agentSessionLabel({ auth: "api_key", status: "API key" })).toBe(
      "signed in"
    )
  })

  it("maps installed or missing agents to not signed in", () => {
    expect(agentSessionLabel({ auth: "none", status: "installed" })).toBe(
      "not signed in"
    )
    expect(agentSessionLabel({ auth: "none", status: "none" })).toBe(
      "not signed in"
    )
  })
})
