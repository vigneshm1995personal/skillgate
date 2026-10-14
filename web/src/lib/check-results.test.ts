import { describe, expect, it } from "vitest"

import {
  checkHeadline,
  extraFailWhy,
  happenedLine,
  lowConfidenceWarning,
  customerGateCopy,
  plainAdviceCopy,
  stripRepeatedHeadline,
  missingJudgeAnswersLine,
  openedCheckAnswers,
  pathOpenedLine,
  scoredByFromJudge,
  scoredByLine,
  suiteUnsureWarning,
} from "./check-results"
import type { TaskResult } from "./types"

const passTask: TaskResult = {
  id: "extract-text",
  prompt: "Extract the text from hello.pdf and save it to output/extracted.txt.",
  status: "done",
  passed: true,
  judge: {
    status: "completed",
    model: "typesafe-ai/jev",
    answers: {
      task_completion: { choice: "Fully completed" },
      correctness: { choice: "Correct" },
      instruction_adherence: { choice: "Fully followed" },
      evidence_action_validity: { choice: "Fully supported" },
      result_quality: { choice: "Clear and complete" },
    },
  },
}

describe("happenedLine", () => {
  it("uses Output matched what was expected on pass", () => {
    expect(happenedLine(passTask)).toBe("Output matched what was expected.")
  })

  it("says no skill was picked on a passing no-trigger check", () => {
    expect(
      happenedLine({
        id: "no-trigger-unrelated",
        passed: true,
        status: "done",
        expect_skill: null,
        selected_skill: null,
      })
    ).toBe("No skill was picked, as expected.")
  })

  it("does not flash no-skill-picked on queued or should-trigger rows", () => {
    expect(
      happenedLine({
        id: "extract-hello",
        status: "queued",
        passed: null,
        expect_skill: null,
        selected_skill: null,
      })
    ).not.toBe("No skill was picked, as expected.")
    expect(
      happenedLine({
        id: "extract-hello",
        status: "running",
        passed: null,
        prompt: "Extract the text from hello.pdf",
      })
    ).not.toBe("No skill was picked, as expected.")
    expect(
      happenedLine({
        id: "extract-hello",
        status: "done",
        passed: true,
        expect_skill: "pdf",
        selected_skill: "pdf",
      })
    ).toBe("Output matched what was expected.")
  })

  it("prefers a stamped happened line", () => {
    expect(happenedLine({ ...passTask, happened: "Custom pass line." })).toBe(
      "Custom pass line."
    )
  })

  it("uses fail_reason on fail and never goes blank", () => {
    const fail: TaskResult = {
      id: "extract-text",
      passed: false,
      status: "done",
      judge: { fail_reason: "The extraction produced the wrong text." },
      failures: ["Checks: correctness Incorrect (need Correct)"],
    }
    expect(happenedLine(fail)).toBe("The extraction produced the wrong text.")
  })

  it("uses the skip reason when one exists", () => {
    expect(
      happenedLine({
        id: "extract-text",
        skipped: true,
        passed: false,
        status: "done",
        judge: { fail_reason: "Stopped early." },
      })
    ).toBe("Stopped early.")
    expect(
      happenedLine({
        id: "extract-text",
        skipped: true,
        passed: false,
        status: "done",
      })
    ).toBe("Skipped")
  })

  it("turns a Checks dump into plain words before advice", () => {
    const fail: TaskResult = {
      id: "extract-text",
      passed: false,
      status: "done",
      failures: ["Checks: correctness Incorrect (need Correct)"],
      advice: { why: "The file did not match." },
    }
    expect(happenedLine(fail)).toBe("Got it right? Incorrect.")
  })

  it("ignores a generic stamp and uses the Checks dump in plain words", () => {
    const fail: TaskResult = {
      id: "extract-text",
      passed: false,
      status: "done",
      happened: "This check did not pass.",
      judge: {
        reasons: [
          'Checks: correctness Incorrect (need Correct) — The file was expected to contain "Goodbye Skill Gate."',
        ],
        cells: {
          correctness: {
            label: "Got it right?",
            choice: "Incorrect",
            reason: 'The file was expected to contain "Goodbye Skill Gate."',
          },
        },
      },
      failures: [
        'Checks: correctness Incorrect (need Correct) — The file was expected to contain "Goodbye Skill Gate."',
      ],
    }
    expect(happenedLine(fail)).toBe(
      'The file was expected to contain "Goodbye Skill Gate."'
    )
    expect(happenedLine(fail)).not.toBe("This check did not pass.")
  })
})

describe("extraFailWhy", () => {
  it("does not repeat the What happened sentence", () => {
    const fail: TaskResult = {
      id: "a",
      passed: false,
      judge: { fail_reason: "Wrong text." },
    }
    expect(happenedLine(fail)).toBe("Wrong text.")
    expect(extraFailWhy(fail)).toBeNull()
    const coded: TaskResult = {
      id: "extract-hello",
      prompt: "Extract the text from hello.pdf.",
      passed: false,
      happened: "blocker skill_trigger (need none)",
      judge: { fail_reason: "blocker skill_trigger (need none)" },
    }
    expect(happenedLine(coded)).toMatch(/didn't start/)
    expect(extraFailWhy(coded)).toBeNull()
  })

  it("stays silent on skipped checks", () => {
    expect(
      extraFailWhy({
        id: "a",
        passed: false,
        skipped: true,
        judge: { fail_reason: "Stopped early." },
      })
    ).toBeNull()
  })
})

describe("scoredByLine", () => {
  it("reads stamped scored_by first as customer copy", () => {
    expect(
      scoredByLine({
        scored_by: "OpenAI (your key) scored this run.",
        skill: "pdf",
        passed_count: 1,
        task_count: 1,
        tasks: [passTask],
      })
    ).toBe("Scored by the judge")
    expect(
      scoredByLine({
        scored_by: "Scored by OpenAI Decisions",
        skill: "pdf",
        passed_count: 1,
        task_count: 1,
        tasks: [passTask],
      })
    ).toBe("Scored by the judge")
    expect(
      scoredByLine({
        scored_by: "OpenAI couldn't score this run. Your OpenAI account is out of credits.",
        skill: "pdf",
        passed_count: 0,
        task_count: 1,
        tasks: [passTask],
      })
    ).toMatch(/^The judge couldn't score this run\./)
  })

  it("hides leftover skip-judge copy from older JSONL rows", () => {
    expect(
      scoredByLine({
        scored_by: "This is not a live model.",
        skill: "pdf",
        passed_count: 1,
        task_count: 1,
        tasks: [passTask],
      })
    ).toBe("Older run (before live-only checks)")
    expect(
      scoredByLine({
        scored_by: "Built-in checker scored this run.",
        skill: "pdf",
        passed_count: 1,
        task_count: 1,
        tasks: [passTask],
      })
    ).toBe("Older run (before live-only checks)")
  })

  it("maps skip scoring without hard-coding the UI to one scorer", () => {
    expect(scoredByFromJudge(passTask.judge)).toBe("Scored by the judge")
    expect(
      scoredByFromJudge({
        provider: "openai",
        backend: "decisions",
        model: "gpt-6-luna",
        status: "completed",
        answers: passTask.judge?.answers,
      })
    ).toBe("Scored by the judge")
    expect(
      scoredByFromJudge({
        provider: "openai",
        backend: "decisions",
        model: "openai/gpt-6-luna-decisions",
        display_name: "OpenAI Decisions via Vercel AI Gateway (your key)",
        status: "completed",
        answers: passTask.judge?.answers,
      })
    ).toBe("Scored by the judge")
  })

  it("does not show gateway plumbing or raw model ids", () => {
    const line = scoredByFromJudge({
      provider: "openai",
      backend: "decisions",
      model: "openai/gpt-4o-mini",
      display_name: "OpenAI Decisions via Vercel AI Gateway (your key)",
      status: "completed",
      answers: passTask.judge?.answers,
    })
    expect(line).toBe("Scored by the judge")
    expect(line).not.toMatch(/gateway|openai\/|your key|OpenAI|Vercel|gpt-6-luna/i)
    expect(
      scoredByLine({
        scored_by: "The skill ran live. Quality was not scored.",
        skill: "pdf",
        passed_count: 1,
        task_count: 1,
        tasks: [passTask],
      })
    ).toBe("Quality was not scored")
  })
})

describe("pathOpenedLine", () => {
  it("shows the path ordinal when present", () => {
    expect(
      pathOpenedLine({
        ...passTask,
        judge: {
          ...passTask.judge,
          soft_answers: { path_efficiency: { choice: "Efficient" } },
        },
      })
    ).toBe("Direct")
  })

  it("omits Path when there is no ordinal and no steps — never Not available", () => {
    expect(pathOpenedLine(passTask)).toBeNull()
    expect(
      pathOpenedLine({
        ...passTask,
        metrics: { path: { steps: 0, had_path: false } },
      })
    ).toBeNull()
    expect(JSON.stringify(pathOpenedLine(passTask))).not.toMatch(/Not available/i)
  })

  it("explains when a path existed but recorded no steps", () => {
    expect(
      pathOpenedLine({
        ...passTask,
        metrics: { path: { steps: 0, had_path: true } },
      })
    ).toBe("This check did not record any steps.")
  })

  it("omits Path when steps exist but there is no ordinal", () => {
    expect(
      pathOpenedLine({
        ...passTask,
        metrics: { path: { steps: 4, had_path: true } },
      })
    ).toBeNull()
  })

  it("marks Path Not checked when the script never ran", () => {
    expect(
      pathOpenedLine({
        id: "extract-hello",
        passed: false,
        status: "done",
        happened: "blocker skill_trigger (need none)",
        judge: {
          soft_answers: { path_efficiency: { choice: "Efficient" } },
        },
        metrics: { path: { steps: 0, had_path: false } },
      })
    ).toBe("Not checked")
  })
})

describe("openedCheckAnswers / low confidence", () => {
  it("lists the five plain-words labels", () => {
    const rows = openedCheckAnswers(passTask)
    expect(rows.map((row) => row.label)).toEqual([
      "Got the job done?",
      "Got it right?",
      "Followed the rules?",
      "Used the right evidence/actions?",
      "Delivered a good result?",
    ])
    expect(rows[1].answer).toBe("Correct")
  })

  it("appends extra scoring answers after the built-in five", () => {
    const rows = openedCheckAnswers({
      ...passTask,
      judge: {
        ...passTask.judge,
        answers: {
          ...passTask.judge!.answers!,
          numbers_match: { probability: 0.9 },
        },
        questions: {
          numbers_match: { instructions: "Do the totals match?" },
        },
      },
    })
    expect(rows.map((row) => row.label)).toEqual([
      "Got the job done?",
      "Got it right?",
      "Followed the rules?",
      "Used the right evidence/actions?",
      "Delivered a good result?",
      "Do the totals match?",
    ])
    expect(
      openedCheckAnswers({
        ...passTask,
        judge: {
          ...passTask.judge,
          cells: {
            ...passTask.judge!.cells,
            totals_ok: { label: "Are the totals OK?", probability: 0.91 },
          },
        },
      }).at(-1)
    ).toEqual({
      id: "totals_ok",
      label: "Are the totals OK?",
      answer: "0.91",
    })
  })

  it("names a chosen scoring provider and not Auto OpenAI", () => {
    expect(
      scoredByFromJudge({
        provider: "jev",
        chosen: true,
        status: "completed",
        answers: passTask.judge?.answers,
      })
    ).toBe("Scored by Jev")
    expect(
      scoredByFromJudge({
        provider: "openai",
        chosen: false,
        status: "completed",
        answers: passTask.judge?.answers,
      })
    ).toBe("Scored by the judge")
  })

  it("warns on low confidence for an otherwise-Pass OpenAI cell and not for Jev", () => {
    expect(lowConfidenceWarning(passTask)).toBeNull()
    expect(
      lowConfidenceWarning({
        ...passTask,
        judge: {
          provider: "openai",
          backend: "decisions",
          answers: {
            ...passTask.judge!.answers!,
            correctness: { choice: "Correct", confidence: 0.42 },
          },
        },
      })
    ).toBe("The judge wasn't sure about this one")
    expect(
      suiteUnsureWarning({
        tasks: [
          {
            ...passTask,
            judge: {
              provider: "openai",
              answers: {
                ...passTask.judge!.answers!,
                task_completion: { choice: "Fully completed" },
              },
            },
          },
        ],
      })
    ).toBe("The judge wasn't sure about this one")
    expect(
      lowConfidenceWarning({
        ...passTask,
        judge: {
          ...passTask.judge,
          answers: {
            ...passTask.judge!.answers!,
            correctness: { choice: "Correct", confidence: 0.2 },
          },
        },
      })
    ).toBeNull()
    expect(
      suiteUnsureWarning({
        tasks: [
          {
            ...passTask,
            judge: {
              ...passTask.judge,
              answers: {
                ...passTask.judge!.answers!,
                correctness: { choice: "Correct", confidence: 0.2 },
              },
            },
          },
        ],
      })
    ).toBeNull()
  })

  it("lists five answers from cells when answers keys are incomplete", () => {
    const fail: TaskResult = {
      id: "extract-text",
      passed: false,
      status: "done",
      judge: {
        cells: {
          task_completion: { choice: "Fully completed" },
          correctness: { choice: "Incorrect" },
          instruction_adherence: { choice: "Violated" },
          evidence_action_validity: { choice: "Fully supported" },
          result_quality: { choice: "Significant issues" },
        },
      },
    }
    expect(openedCheckAnswers(fail).map((row) => row.answer)).toEqual([
      "Fully completed",
      "Incorrect",
      "Violated",
      "Fully supported",
      "Significant issues",
    ])
  })

  it("does not show a raw confidence number", () => {
    const warning = lowConfidenceWarning({
      ...passTask,
      judge: {
        provider: "openai",
        backend: "decisions",
        answers: {
          ...passTask.judge!.answers!,
          correctness: { choice: "Correct", confidence: 0.13 },
        },
      },
    })
    expect(warning).toBe("The judge wasn't sure about this one")
    expect(warning).not.toMatch(/0\.13|OpenAI was unsure/)
  })

  it("marks rubric answers Not checked when the script never ran", () => {
    const neverRan: TaskResult = {
      id: "extract-hello",
      prompt: "Extract the text from hello.pdf.",
      passed: false,
      status: "done",
      happened: "blocker skill_trigger (need none)",
      failures: ["blocker skill_trigger (need none)"],
      judge: {
        cells: {
          task_completion: { choice: "Fully completed" },
          correctness: { choice: "Correct" },
          instruction_adherence: { choice: "Fully followed" },
          evidence_action_validity: { choice: "Fully supported" },
          result_quality: { choice: "Clear and complete" },
        },
        soft_answers: { path_efficiency: { choice: "Efficient" } },
      },
      metrics: { path: { steps: 0, had_path: false } },
    }
    expect(openedCheckAnswers(neverRan).map((row) => row.answer)).toEqual([
      "Not checked",
      "Not checked",
      "Not checked",
      "Not checked",
      "Not checked",
    ])
    expect(pathOpenedLine(neverRan)).toBe("Not checked")
  })

  it("says Correctly skipped on a passing no-trigger check", () => {
    const skipped: TaskResult = {
      id: "no-trigger-unrelated",
      passed: true,
      status: "done",
      expect_skill: null,
      selected_skill: null,
      judge: {
        status: "skip",
        answers: {
          task_completion: { choice: "Correctly skipped" },
          correctness: { choice: "Correctly skipped" },
          instruction_adherence: { choice: "Correctly skipped" },
          evidence_action_validity: { choice: "Correctly skipped" },
          result_quality: { choice: "Correctly skipped" },
        },
      },
    }
    expect(openedCheckAnswers(skipped).map((row) => row.answer)).toEqual([
      "Correctly skipped",
      "Correctly skipped",
      "Correctly skipped",
      "Correctly skipped",
      "Correctly skipped",
    ])
  })
})

describe("checkHeadline", () => {
  it("uses the first sentence of the prompt", () => {
    expect(checkHeadline(passTask)).toBe(
      "Extract the text from hello.pdf and save it to output/extracted.txt."
    )
  })

  it("shows the check text, not the internal id, for try-outs", () => {
    expect(
      checkHeadline({
        id: "report-from-bullets",
        prompt: "Turn bullets.md into a short markdown status report at output/status-report.md.",
      })
    ).toBe("Turn bullets.md into a short markdown status report at output/status-report.md.")
    expect(
      checkHeadline({
        id: "report-from-bullets",
        prompt: "Turn bullets.md into a short markdown status report at output/status-report.md.",
      })
    ).not.toMatch(/report-from-bullets/)
  })

  it("does not add a period after an ellipsis", () => {
    const long =
      "Create a PDF at output/status.pdf titled Q3 Status that contains the sentence All systems are go and then some extra words to force truncation here."
    const headline = checkHeadline({ id: "status", prompt: long })
    expect(headline.endsWith("…")).toBe(true)
    expect(headline.endsWith("….")).toBe(false)
  })
})

describe("missingJudgeAnswersLine", () => {
  it("says so in one sentence when there are no five answers", () => {
    expect(
      missingJudgeAnswersLine({
        id: "standup",
        passed: false,
        status: "done",
        failures: ["sandbox timed out"],
      })
    ).toBe("The checker didn't score this check because it ran out of time.")
    expect(
      missingJudgeAnswersLine({
        id: "extract-hello",
        prompt: "Extract the text from hello.pdf.",
        passed: false,
        status: "done",
        happened: "blocker skill_trigger (need none)",
        failures: ["blocker skill_trigger (need none)"],
      })
    ).toBe(
      "The checker didn't score this check because the skill never started."
    )
    expect(missingJudgeAnswersLine(passTask)).toBeNull()
  })

  it("uses happened when leftover skill_trigger disagrees with a run that used the skill", () => {
    const task: TaskResult = {
      id: "create-status",
      prompt:
        "Create a PDF at output/status.pdf titled Q3 Status that contains the sentence All systems are go.",
      passed: false,
      status: "done",
      happened: "outcome partial (need on_target)",
      failures: ["blocker skill_trigger (need none)"],
      judge: { status: "completed", model: "typesafe-ai/jev" },
      metrics: { path: { steps: 7, had_path: true } },
      spans: [
        {
          name: "tool.shell",
          attributes: [
            {
              key: "gen_ai.tool.call.arguments",
              value: { stringValue: "scripts/create_pdf.py output/status.pdf" },
            },
          ],
        },
      ],
    }
    expect(happenedLine(task)).toBe("The PDF was only partly right.")
    expect(missingJudgeAnswersLine(task)).toBe("The PDF was only partly right.")
    expect(missingJudgeAnswersLine(task)).not.toBe(
      "The checker didn't score this check because the skill never started."
    )
  })

  it("still says never-started when the transcript only has a completed agent message", () => {
    const task: TaskResult = {
      id: "extract-hello",
      prompt: "Extract the text from hello.pdf.",
      passed: false,
      status: "done",
      happened: "blocker skill_trigger (need none)",
      failures: ["blocker skill_trigger (need none)"],
      transcript:
        '{"type":"item.completed","item":{"type":"agent_message","text":"No matching skill."}}',
    }
    expect(missingJudgeAnswersLine(task)).toBe(
      "The checker didn't score this check because the skill never started."
    )
  })

  it("still says the skill never started when the record shows it did not run", () => {
    const task: TaskResult = {
      id: "extract-hello",
      prompt: "Extract the text from hello.pdf.",
      passed: false,
      status: "done",
      happened: "blocker skill_trigger (need none)",
      failures: ["blocker skill_trigger (need none)"],
    }
    expect(happenedLine(task)).toMatch(/didn't start/)
    expect(missingJudgeAnswersLine(task)).toBe(
      "The checker didn't score this check because the skill never started."
    )
  })

  it("does not infer never-started from leftover trigger codes when path shows a run", () => {
    const task: TaskResult = {
      id: "create-status",
      prompt: "Create a PDF at output/status.pdf titled Q3 Status.",
      passed: false,
      status: "done",
      happened: "This check did not pass.",
      failures: ["blocker skill_trigger (need none)"],
      metrics: { path: { steps: 7, had_path: true } },
    }
    expect(missingJudgeAnswersLine(task)).not.toBe(
      "The checker didn't score this check because the skill never started."
    )
  })
})

describe("customerGateCopy", () => {
  it("rewrites leftover developer warnings into gentle notes", () => {
    expect(customerGateCopy("All checks passed.")).toBe("All checks passed.")
    expect(
      customerGateCopy("This run used draft checks, not the saved Dataset.")
    ).toBe("This run used the current checks, which aren't the saved Dataset yet.")
    expect(customerGateCopy("Gate is red — Deploy is blocked.")).toBe(
      "Get a passing run to unlock Deploy."
    )
    expect(customerGateCopy("Get a passing run to unlock Install.")).toBe(
      "Get a passing run to unlock Deploy."
    )
    expect(
      customerGateCopy("Case extract-hello is missing golden file evals/goldens/extract-hello.txt.")
    ).toBe("This check is missing its expected output file.")
    expect(customerGateCopy("Set SKILLGATE_TASK before running.")).toBe(
      "Set the task before running."
    )
    expect(
      customerGateCopy("Missing fixture evals/fixtures/hello.pdf for this check.")
    ).not.toMatch(/evals\//)
    expect(customerGateCopy("BYO LLM returned 429")).toMatch(
      /out of credit|rate-limited/i
    )
    expect(
      customerGateCopy(
        "Check OPENAI_API_KEY or AI_GATEWAY_API_KEY and SKILLGATE_MODEL in `.env`."
      )
    ).toMatch(/Settings/)
    expect(
      customerGateCopy(
        "Check OPENAI_API_KEY or AI_GATEWAY_API_KEY and SKILLGATE_MODEL in `.env`."
      )
    ).not.toMatch(/OPENAI_API_KEY|\.env/)
  })
})

describe("plainAdviceCopy", () => {
  it("rewrites leftover developer suggest/advice lines", () => {
    expect(
      plainAdviceCopy("don't switch to the good pdf twin")
    ).toBe("don't switch to a working copy of this skill")
    expect(
      plainAdviceCopy("The agent only sees name + description before opening SKILL.md.")
    ).toBe(
      "Before it reads the instructions, the agent only sees the skill's name and description."
    )
    expect(plainAdviceCopy("Stay on `pdf-sabotaged`.")).toBe("Stay on pdf-sabotaged.")
    expect(
      plainAdviceCopy("Replace the description, then run `skillgate check` on this same skill.")
    ).toBe("Replace the description.")
    expect(
      plainAdviceCopy("don't switch to the a working copy of this skill")
    ).toBe("don't switch to a working copy of this skill")
  })

  it("drops a duplicated Stay on this skill heading from the body", () => {
    expect(
      stripRepeatedHeadline(
        "Stay on this skill. Before it reads the instructions, the agent only sees the skill's name and description.",
        "Stay on this skill"
      )
    ).toBe(
      "Before it reads the instructions, the agent only sees the skill's name and description."
    )
  })
})

describe("scorerCodeToPlain / happenedLine codes", () => {
  it("maps stored scorer codes from pdf-sabotaged runs", () => {
    const fail: TaskResult = {
      id: "extract-hello",
      prompt: "Extract the text from hello.pdf and save it to output/extracted.txt.",
      passed: false,
      status: "done",
      happened: "blocker skill_trigger (need none)",
    }
    expect(happenedLine(fail)).toBe(
      "The skill didn't start for this request — its description doesn't match what was asked."
    )
    expect(
      happenedLine({
        id: "status-pdf",
        prompt: "Create a PDF at output/status.pdf titled Q3 Status.",
        passed: false,
        status: "done",
        happened: "outcome partial (need on_target)",
      })
    ).toBe("The PDF was only partly right.")
  })
})
