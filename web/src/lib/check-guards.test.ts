import { describe, expect, it } from "vitest"

import { authenticFixtureDefaults, leakedPdfDemoNames, startBlockedIssues } from "./check-guards"

describe("startBlockedIssues", () => {
  it("does not block a no-trigger check that still has leftover expected output", () => {
    expect(
      startBlockedIssues(
        [
          {
            id: "no-trigger-unrelated",
            prompt:
              "Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.",
            should_trigger: false,
            output_path: "output/notes.txt",
            contains: "Meeting notes",
            golden_path: "evals/goldens/trigger-notes-pdf.txt",
          },
        ],
        false,
        null
      )
    ).toEqual([])
  })
})

const PDF_DEMO = [
  "evals/fixtures/alpha.pdf",
  "evals/fixtures/beta.pdf",
  "evals/fixtures/hello.pdf",
  "evals/fixtures/invoice.pdf",
  "evals/fixtures/notes.pdf",
]

describe("authenticFixtureDefaults", () => {
  it("does not list the pdf example files on csv-cleaner", () => {
    const skill = {
      name: "csv-cleaner",
      slug: "csv-cleaner",
      id: "csv-cleaner",
      absolute: "/tmp/proj/skills/csv-cleaner",
      fixture_defaults: PDF_DEMO.map((src) => ({ src })),
      pack_files: [
        { path: "evals/fixtures/orders.csv", bytes: 12 },
        ...PDF_DEMO.map((path) => ({ path, bytes: 800 })),
      ],
    }
    expect(authenticFixtureDefaults(skill).map((item) => item.path)).toEqual([
      "evals/fixtures/orders.csv",
    ])
    expect(leakedPdfDemoNames(skill)).toEqual([
      "alpha.pdf",
      "beta.pdf",
      "hello.pdf",
      "invoice.pdf",
      "notes.pdf",
    ])
  })

  it("keeps a single hello.pdf that is not the full pdf example set", () => {
    const skill = {
      name: "notes",
      slug: "notes",
      id: "notes",
      pack_files: [{ path: "evals/fixtures/hello.pdf", bytes: 800 }],
    }
    expect(authenticFixtureDefaults(skill).map((item) => item.path)).toEqual([
      "evals/fixtures/hello.pdf",
    ])
  })

  it("keeps the pdf example's own sample files", () => {
    const skill = {
      name: "pdf",
      slug: "pdf",
      id: "pdf",
      absolute: "/tmp/proj/skills/pdf",
      fixture_defaults: PDF_DEMO.map((src) => ({ src })),
    }
    expect(authenticFixtureDefaults(skill).map((item) => item.path)).toEqual(PDF_DEMO)
    expect(leakedPdfDemoNames(skill)).toEqual([])
  })
})
