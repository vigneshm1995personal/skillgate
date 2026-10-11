import { describe, expect, it } from "vitest"

import { canPinCheck, expectedFieldValue } from "./case-pack"

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
