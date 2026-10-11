import { describe, expect, it } from "vitest"

import {
  canPinCheck,
  expectedFieldValue,
  noTriggerOutputWarning,
  showsExpectedOutputFields,
} from "./case-pack"

describe("canPinCheck", () => {
  it("allows a completion check that already has a golden file", () => {
    expect(
      canPinCheck({
        prompt: "Extract hello.pdf",
        should_trigger: true,
        output_path: "output/extracted.txt",
        golden_path: "evals/goldens/extract-hello.txt",
      })
    ).toBe(true)
  })

  it("allows Dataset expected output", () => {
    expect(
      canPinCheck({
        prompt: "Extract hello.pdf",
        should_trigger: true,
        output_path: "output/extracted.txt",
        contains: "Hello Skill Gate",
      })
    ).toBe(true)
  })
})

describe("expectedFieldValue", () => {
  it("names the expected-output file when contains is empty", () => {
    expect(
      expectedFieldValue({
        golden_path: "evals/goldens/merge-alpha-beta.pdf",
      })
    ).toBe("Matches file merge-alpha-beta.pdf")
  })

  it("keeps an explicit contains string", () => {
    expect(
      expectedFieldValue({
        contains: "Hello Skill Gate",
        golden_path: "evals/goldens/extract-hello.txt",
      })
    ).toBe("Hello Skill Gate")
  })
})

describe("no-trigger expected output", () => {
  const leftover = {
    id: "no-trigger-unrelated",
    prompt: "Write a pytest for a FastAPI /health endpoint. Do not touch any PDFs.",
    should_trigger: false,
    output_path: "output/notes.txt",
    contains: "Meeting notes",
    golden_path: "evals/goldens/trigger-notes-pdf.txt",
  }

  it("hides expected-output fields on a no-trigger check", () => {
    expect(showsExpectedOutputFields(leftover)).toBe(false)
    expect(
      showsExpectedOutputFields({
        prompt: "Extract notes.pdf",
        should_trigger: true,
        output_path: "output/notes.txt",
      })
    ).toBe(true)
  })

  it("warns in plain words that leftover output on a no-trigger check is ignored", () => {
    const warning = noTriggerOutputWarning(leftover)
    expect(warning).toMatch(/ignored/i)
    expect(warning).not.toMatch(/output_path|golden|contains/)
    expect(
      noTriggerOutputWarning({
        prompt: leftover.prompt,
        should_trigger: false,
      })
    ).toBeNull()
  })
})
