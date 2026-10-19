import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

import { paintOf } from "@/components/dashboard/eval-mosaic"
import { historyResultLabel } from "@/lib/history-result"
import { runButtonTotal } from "@/lib/run-label"

const webSrc = dirname(fileURLToPath(import.meta.url))

describe("unscored runs", () => {
  it("labels a run that did not score as not run", () => {
    expect(historyResultLabel(null)).toEqual({ text: "Not run", tone: "not-run" })
    expect(historyResultLabel(undefined)).toEqual({ text: "Not run", tone: "not-run" })
    expect(historyResultLabel(true).text).toBe("Pass")
    expect(historyResultLabel(false).text).toBe("Fail")
  })

  it("does not paint an unscored run red on the heatmap", () => {
    expect(paintOf({ passed: null, status: "error" })).toBe("skip")
    expect(paintOf({ passed: false, status: "error" })).toBe("fail")
    expect(paintOf({ passed: true, status: "done" })).toBe("pass")
    const mosaic = readFileSync(
      join(webSrc, "../components/dashboard/eval-mosaic.tsx"),
      "utf8"
    )
    expect(mosaic).toContain("paintOf(run)")
    const history = readFileSync(
      join(webSrc, "../components/dashboard/history-page.tsx"),
      "utf8"
    )
    expect(history).toContain("historyResultLabel")
    const evalPage = readFileSync(
      join(webSrc, "../components/dashboard/eval-page.tsx"),
      "utf8"
    )
    expect(evalPage).toContain("runButtonTotal")
  })
})

describe("draft-only run label", () => {
  it("does not count draft checks as a case to run", () => {
    expect(
      runButtonTotal({
        running: false,
        taskCount: 1,
        checks: [{ bank_status: "draft" }],
      })
    ).toBe(0)
    expect(
      runButtonTotal({
        running: false,
        taskCount: 1,
        checks: [{ bank_status: "pinned" }],
      })
    ).toBe(1)
  })
})
