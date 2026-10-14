import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const componentsRoot = join(dirname(fileURLToPath(import.meta.url)))

describe("dataset import UI", () => {
  it("disables confirm when preview rows have errors", () => {
    const src = readFileSync(
      join(componentsRoot, "dataset-import-dialog.tsx"),
      "utf8"
    )
    expect(src).toMatch(/datasetImportFooter/)
    expect(src).toMatch(/disabled=\{busy \|\| !footer\.canImport\}/)
    expect(src).toMatch(/dataset-import-block-hint/)
    const state = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "../../lib/dataset-import-state.ts"),
      "utf8"
    )
    expect(state).toMatch(/Fix \$\{count\} row/)
  })

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
