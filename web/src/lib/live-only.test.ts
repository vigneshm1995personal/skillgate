import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const lib = dirname(fileURLToPath(import.meta.url))

function read(name: string): string {
  return readFileSync(join(lib, name), "utf8")
}

describe("Start Evaluations live-only guard", () => {
  it("always sends live true and demo false, and throws unless the run is live", () => {
    const provider = [
      read("dashboard-helpers.ts"),
      read("use-eval-session.ts"),
      read("dashboard-provider.tsx"),
    ].join("\n")

    expect(provider).toContain("live: true")
    expect(provider).toContain("demo: false")
    expect(provider).not.toContain("demo: !live")
    expect(provider).not.toContain("live: Boolean(status?.has_key)")
    expect(provider.split("live: true").length - 1).toBeGreaterThanOrEqual(3)

    const startIdx = provider.indexOf("const startEvaluations")
    const pasteIdx = provider.indexOf("const runAfterPossiblePaste")
    const runNowIdx = provider.indexOf("const payload =")
    expect(startIdx).toBeGreaterThanOrEqual(0)
    expect(pasteIdx).toBeGreaterThan(startIdx)
    expect(provider.slice(startIdx, pasteIdx)).toContain("live: true")
    expect(provider.slice(pasteIdx, pasteIdx + 1800)).toContain("live: true")
    const payload = provider.slice(runNowIdx, runNowIdx + 200)
    expect(payload).toContain("live: true")
    expect(payload).toContain("demo: false")
    expect(provider).toContain("harness: harnessPref")

    const session = read("use-eval-session.ts")
    const runNow = session.slice(
      session.indexOf("const runNow"),
      session.indexOf("const runThisCheck")
    )
    expect(runNow).toContain("liveFlag !== true")
    expect(runNow).toContain(
      'throw new Error("Start Evaluations is live-only.")'
    )
    const runThis = session.slice(
      session.indexOf("const runThisCheck"),
      session.indexOf("const openHistoryRun")
    )
    expect(runThis).toContain("live: true")
    expect(runThis).not.toContain("Boolean(status?.has_key)")

    const evalPage = readFileSync(
      join(lib, "../components/dashboard/eval-page.tsx"),
      "utf8"
    )
    const button = evalPage.slice(
      evalPage.indexOf('id="btn-run"'),
      evalPage.indexOf('id="btn-run"') + 400
    )
    expect(button).toContain("!status?.has_key")
  })
})
