import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const componentsRoot = join(dirname(fileURLToPath(import.meta.url)))

describe("dataset import UI", () => {
  it("exposes Import dataset on the skill page", () => {
    const src = readFileSync(
      join(componentsRoot, "skill-detail-page.tsx"),
      "utf8"
    )
    expect(src).toMatch(/Import dataset/)
    expect(src).toMatch(/DatasetImportDialog/)
    expect(src).toMatch(/btn-import-dataset-detail/)
  })
})
