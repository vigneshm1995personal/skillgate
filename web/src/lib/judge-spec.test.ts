import { describe, expect, it } from "vitest"

import {
  BUILTIN_QUESTIONS,
  MAX_SCORING_QUESTIONS,
  duplicateExtraIds,
  totalQuestionCount,
} from "./judge-spec"

describe("judge spec", () => {
  it("counts six built-ins plus extras", () => {
    expect(BUILTIN_QUESTIONS).toHaveLength(6)
    expect(MAX_SCORING_QUESTIONS).toBe(20)
    expect(
      totalQuestionCount(
        { extra_questions: [{ id: "pack_q", type: "predicate", ask: "Pack?" }] },
        { extra_questions: [{ id: "case_q", type: "predicate", ask: "Case?" }] }
      )
    ).toBe(8)
  })

  it("flags a new extra that reuses an existing id", () => {
    expect(
      duplicateExtraIds([
        { id: "fileexists", type: "predicate", ask: "Did the file exist?" },
        { id: "fileexists", type: "score", ask: "Clarity 1-5" },
      ])
    ).toEqual(["fileexists"])
    expect(
      duplicateExtraIds([{ id: "clarity", type: "score", ask: "Clarity 1-5" }])
    ).toEqual([])
  })
})
