import { describe, expect, it } from "vitest"

import { canPinCheck } from "./case-pack"

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
