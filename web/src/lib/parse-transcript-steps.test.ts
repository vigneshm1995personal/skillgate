import { readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

import { collapseAssistantSpans } from "./collapse-assistant-spans"
import {
  glueAssistantDelta,
  jsonlToSpans,
  pickTimelineSteps,
  previewPlainText,
  spansToTimelineSteps,
  truncateAtWord,
} from "./parse-transcript-steps"

const FIXTURE = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "../../../tests/fixtures/cursor_stream_partial_run.jsonl"),
  "utf8"
)

const COMPLETED = [
  "I generated the status report at `output/status-report.md`.",
  "The instructions say to avoid files.",
  "It's a broken copy of the PDF skill.",
  "I created output/status.pdf. The tools support that.",
]

const CREATE_STATUS = [
  "The selected skill is a deliberately broken meal-planner twin whose steps don't apply to making a PDF, so I'll ignore them and create the PDF directly.",
  "The bundled `create_pdf.py` script looks sound, so I'll use it and then check the text made it into the file.",
  'I created `output/status.pdf`. It has a "Q3 Status" heading followed by the sentence "All systems are go." I checked by extracting the text back out of the PDF, and both lines are there.\n\nThe selected `pdf-sabotaged` skill is broken on purpose. Its description is about meal planning, and its steps say to avoid files, run a merge script with `--please-fail`, and never write to `output/`. I didn\'t follow those steps. The skill does include a working `create_pdf.py` script, so I used that to build the PDF.\n\n"Q3 Status" is the heading on the page, but it isn\'t set as the PDF\'s document-title property, because the script doesn\'t support that.',
]

function assistantMessages(transcript: string): string[] {
  return jsonlToSpans(transcript)
    .filter((span) => span.name === "gen_ai.assistant")
    .map(
      (span) =>
        span.attributes?.find((item) => item.key === "gen_ai.assistant.message")?.value
          .stringValue || ""
    )
}

describe("glueAssistantDelta", () => {
  it("concatenates Cursor partials without inserting spaces", () => {
    expect(glueAssistantDelta("The sel", "ected skill")).toBe("The selected skill")
    expect(glueAssistantDelta("I ", "'m")).toBe("I 'm")
    expect(glueAssistantDelta("I", "'m")).toBe("I'm")
    expect(glueAssistantDelta("pd", "f")).toBe("pdf")
  })
})

describe("cursor completed-message source of truth", () => {
  it("uses each completed message exactly, with no duplicates or mid-word starts", () => {
    const msgs = assistantMessages(FIXTURE)
    expect(msgs).toEqual(COMPLETED)
    for (const msg of msgs) {
      expect(msg.startsWith("Iated")).toBe(false)
      expect(msg.startsWith("'s")).toBe(false)
      expect(msg.startsWith("ps ")).toBe(false)
      expect(msg.startsWith("s ")).toBe(false)
      const copies = msg.split("I created output/status.pdf").length - 1
      expect(copies).toBeLessThan(2)
    }
  })

  it("replaces live partials with the completed text when the turn finishes", () => {
    const live = [
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 1,
        message: { content: [{ type: "text", text: "I " }] },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        message: { content: [{ type: "text", text: "gener" }] },
      }),
    ].join("\n")
    expect(assistantMessages(live)).toEqual(["I gener"])

    const done = [
      live,
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 3,
        model_call_id: "mc-live",
        message: {
          content: [
            {
              type: "text",
              text: "I generated the status report at `output/status-report.md`.",
            },
          ],
        },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 4,
        message: {
          content: [{ type: "text", text: "ated the status report at `output/status-report.md`." }],
        },
      }),
    ].join("\n")
    expect(assistantMessages(done)).toEqual([
      "I generated the status report at `output/status-report.md`.",
    ])
  })

  it("does not drop a new turn that starts with I after It's …", () => {
    const lines = [
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 1,
        model_call_id: "mc-1",
        message: {
          content: [{ type: "text", text: "It's a broken copy of the PDF skill." }],
        },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        message: { content: [{ type: "text", text: "I" }] },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 3,
        message: {
          content: [
            { type: "text", text: " created output/status.pdf. The tools support that." },
          ],
        },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 4,
        model_call_id: "mc-2",
        message: {
          content: [
            { type: "text", text: "I created output/status.pdf. The tools support that." },
          ],
        },
      }),
    ]
    expect(assistantMessages(lines.join("\n"))).toEqual([
      "It's a broken copy of the PDF skill.",
      "I created output/status.pdf. The tools support that.",
    ])
  })

  it("keeps two completed turns that share a prefix through pickTimelineSteps", () => {
    const first = "I'll read the skill now"
    const second = "I'll read the skill now and follow the instructions."
    const transcript = [
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 1,
        model_call_id: "mc-1",
        message: { content: [{ type: "text", text: first }] },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "started",
        tool_call: { readToolCall: { args: { path: "SKILL.md" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        model_call_id: "mc-2",
        message: { content: [{ type: "text", text: second }] },
      }),
    ].join("\n")
    const details = pickTimelineSteps({ transcript })
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(details).toEqual([first, second])
  })

  it("does not drop a later unique message that quotes a prior completed sentence", () => {
    const first =
      "The script exited cleanly but printed nothing, so I'll confirm the output file was actually written."
    const follow =
      "Next I'll inspect messy.csv because the script exited cleanly but printed nothing, so I'll confirm later."
    const details = pickTimelineSteps({
      transcript: "",
      spans: [
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: first } }],
        },
        {
          name: "tool.shell",
          attributes: [{ key: "gen_ai.tool.call.arguments", value: { stringValue: "ls" } }],
        },
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: follow } }],
        },
      ],
    })
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(details).toEqual([first, follow])
  })

  it("does not merge completed turns that share an opening then diverge", () => {
    const first = "I created output/status.pdf now."
    const second = "I created output/status.pdf. Looks ok."
    const lines = [
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 1,
        model_call_id: "mc-1",
        message: { content: [{ type: "text", text: first }] },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "started",
        tool_call: { readToolCall: { args: { path: "SKILL.md" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        model_call_id: "mc-2",
        message: { content: [{ type: "text", text: second }] },
      }),
    ]
    expect(assistantMessages(lines.join("\n"))).toEqual([first, second])
    const stored = pickTimelineSteps({
      transcript: "",
      spans: [
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: first } }],
        },
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: second } }],
        },
      ],
    })
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(stored).toEqual([first, second])
  })

  it("keeps a live turn that quotes a prior completed sentence", () => {
    const first =
      "The script exited cleanly but printed nothing, so I'll confirm the output file was actually written."
    const follow = "I'll confirm the output file was actually written, then stop."
    const lines = [
      JSON.stringify({
        type: "assistant",
        model_call_id: "mc-1",
        message: { content: [{ type: "text", text: first }] },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "started",
        tool_call: { shellToolCall: { args: { command: "ls output/" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        message: { content: [{ type: "text", text: follow }] },
      }),
    ]
    expect(assistantMessages(lines.join("\n"))).toEqual([first, follow])
  })

  it("keeps a live I'll confirm buffer when the new turn has no completed event yet", () => {
    const first =
      "The script exited cleanly but printed nothing, so I'll confirm the output file was actually written."
    const lines = [
      JSON.stringify({
        type: "assistant",
        model_call_id: "mc-1",
        message: { content: [{ type: "text", text: first }] },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "started",
        tool_call: { shellToolCall: { args: { command: "ls" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        message: { content: [{ type: "text", text: "I'll confirm" }] },
      }),
    ]
    expect(assistantMessages(lines.join("\n"))).toEqual([first, "I'll confirm"])
  })

  it("does not drop a new turn whose first delta is I'll confirm from a prior message", () => {
    const first =
      "The script exited cleanly but printed nothing, so I'll confirm the output file was actually written."
    const live = "I'll confirm the sandbox wrote the file, then stop."
    const lines = [
      JSON.stringify({
        type: "assistant",
        model_call_id: "mc-1",
        message: { content: [{ type: "text", text: first }] },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "started",
        tool_call: { shellToolCall: { args: { command: "ls output/" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        message: { content: [{ type: "text", text: "I'll confirm" }] },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 3,
        message: {
          content: [{ type: "text", text: " the sandbox wrote the file, then stop." }],
        },
      }),
      JSON.stringify({
        type: "assistant",
        model_call_id: "mc-2",
        message: { content: [{ type: "text", text: live }] },
      }),
    ]
    expect(assistantMessages(lines.join("\n"))).toEqual([first, live])
  })

  it("drops an uppercase mix leftover of completed texts", () => {
    const first =
      "The script exited cleanly but printed nothing, so I'll confirm the output file was actually written."
    const leftover =
      "Londonleanly but printed nothing, so I'll confirm the output file was actually written."
    const transcript = readFileSync(
      join(
        dirname(fileURLToPath(import.meta.url)),
        "../../../tests/fixtures/stored_spliced_assistant.jsonl"
      ),
      "utf8"
    )
    const second = JSON.parse(transcript.trim().split("\n").at(-1) || "{}").message.content[0]
      .text as string
    const assistant = (text: string) => ({
      name: "gen_ai.assistant" as const,
      attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: text } }],
    })
    const kept = collapseAssistantSpans(
      [assistant(first), assistant(leftover), assistant(second)],
      [first, second]
    )
      .filter((span) => span.name === "gen_ai.assistant")
      .map(
        (span) =>
          span.attributes?.find((item) => item.key === "gen_ai.assistant.message")?.value
            .stringValue || ""
      )
    expect(kept).toEqual([first, second])
  })

  it("keeps unique stored turns that share an opening then diverge at a word", () => {
    const first = "The file was written to output/status.pdf successfully."
    const second = "The file was written to output/status.pdf successfully yesterday."
    const details = pickTimelineSteps({
      transcript: "",
      spans: [
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: first } }],
        },
        {
          name: "tool.shell",
          attributes: [{ key: "gen_ai.tool.call.arguments", value: { stringValue: "ls" } }],
        },
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: second } }],
        },
      ],
    })
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(details).toEqual([first, second])
  })

  it("keeps an unfinished turn whose first delta reuses cleaned and saved", () => {
    const first =
      "The script exited cleanly but printed nothing, so I'll confirm the output file was actually written."
    const transcript = readFileSync(
      join(
        dirname(fileURLToPath(import.meta.url)),
        "../../../tests/fixtures/stored_spliced_assistant.jsonl"
      ),
      "utf8"
    )
    const second = JSON.parse(transcript.trim().split("\n").at(-1) || "{}").message.content[0]
      .text as string
    const live = "cleaned and saved a backup, then I waited on the sandbox."
    const lines = [
      JSON.stringify({
        type: "assistant",
        model_call_id: "mc-1",
        message: { content: [{ type: "text", text: first }] },
      }),
      JSON.stringify({
        type: "assistant",
        message: { content: [{ type: "text", text: second }] },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "started",
        tool_call: { shellToolCall: { args: { command: "ls" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        message: { content: [{ type: "text", text: "cleaned and saved" }] },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 3,
        message: { content: [{ type: "text", text: " a backup, then I waited on the sandbox." }] },
      }),
    ]
    expect(assistantMessages(lines.join("\n"))).toEqual([first, second, live])
  })

  it("keeps two completed turns that share a prefix", () => {
    const lines = [
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 1,
        model_call_id: "mc-1",
        message: { content: [{ type: "text", text: "I'll read the skill now" }] },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "started",
        tool_call: { readToolCall: { args: { path: "SKILL.md" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        model_call_id: "mc-2",
        message: {
          content: [
            { type: "text", text: "I'll read the skill now and follow the instructions." },
          ],
        },
      }),
    ]
    expect(assistantMessages(lines.join("\n"))).toEqual([
      "I'll read the skill now",
      "I'll read the skill now and follow the instructions.",
    ])
  })

  it("does not split an assistant message on tool_call completed", () => {
    const lines = [
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 1,
        message: { content: [{ type: "text", text: "The instruction" }] },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        message: { content: [{ type: "text", text: "s say to avoid files." }] },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "started",
        tool_call: { readToolCall: { args: { path: "create_pdf.py" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 3,
        message: { content: [{ type: "text", text: "The selected skill i" }] },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "completed",
        tool_call: { readToolCall: { args: { path: "create_pdf.py" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 4,
        message: { content: [{ type: "text", text: "s a broken copy of the PDF skill." }] },
      }),
      JSON.stringify({
        type: "assistant",
        model_call_id: "mc-1",
        message: {
          content: [
            { type: "text", text: "The selected skill is a broken copy of the PDF skill." },
          ],
        },
      }),
    ]
    const msgs = assistantMessages(lines.join("\n"))
    expect(msgs[0]).toBe("The instructions say to avoid files.")
    expect(msgs[1]).toBe("The selected skill is a broken copy of the PDF skill.")
    expect(msgs.some((msg) => msg.startsWith("s ") || msg.startsWith("ps "))).toBe(false)
  })
})

describe("pickTimelineSteps", () => {
  it("prefers completed JSONL text over stored fragments", () => {
    const stored = [
      {
        name: "gen_ai.assistant" as const,
        attributes: [
          {
            key: "gen_ai.assistant.message",
            value: { stringValue: "ps say to avoid files" },
          },
        ],
      },
      {
        name: "gen_ai.assistant" as const,
        attributes: [
          {
            key: "gen_ai.assistant.message",
            value: { stringValue: "'s a broken copy of the PDF skill…" },
          },
        ],
      },
    ]
    const steps = pickTimelineSteps({ transcript: FIXTURE, spans: stored })
    const details = steps
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(details).toEqual(COMPLETED)
    expect(details.join("\n")).not.toMatch(/\bps say\b|^'s a broken/m)
  })

  it("shows concatenated raw transcript text when no completed event exists", () => {
    const partials = [
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 1,
        message: { content: [{ type: "text", text: "I ran the sk" }] },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        message: { content: [{ type: "text", text: "ill's bundled script" }] },
      }),
    ].join("\n")
    const steps = pickTimelineSteps({
      transcript: partials,
      spans: [
        {
          name: "gen_ai.assistant",
          attributes: [
            {
              key: "gen_ai.assistant.message",
              value: { stringValue: "I ran the sk ill's bundled script" },
            },
          ],
        },
      ],
    })
    expect(steps[0]?.detail).toBe("I ran the skill's bundled script")
  })

  it("rebuilds the stored pdf-sabotaged create-status task without fragments or dupes", () => {
    const transcript = readFileSync(
      join(
        dirname(fileURLToPath(import.meta.url)),
        "../../../tests/fixtures/pdf_sabotaged_create_status.jsonl"
      ),
      "utf8"
    )
    const stored = [
      {
        name: "gen_ai.assistant" as const,
        attributes: [
          {
            key: "gen_ai.assistant.message",
            value: { stringValue: "ps say to avoid files" },
          },
        ],
      },
      {
        name: "gen_ai.assistant" as const,
        attributes: [
          {
            key: "gen_ai.assistant.message",
            value: {
              stringValue:
                'I created `output/status.pdf`. It has a "Q3 Status" heading followed by the sentence "All systems are go." I checked by extracting the text back out of the PDF, and both lines are there.\n\nThe selected `pdf-sabotaged` skill is broken on purpose. Its description is about meal planning, and its ste, run a merge script with `--please-fail`, and never write to `output/`. I didn\'t follow those steps. The skill does include a working `create_pdf.py` script, so I used that to build the PDF.\n\n"Q3 Status" is the heading on the page, but it isn\'t set as the PDF\'s document-title property, because the script doesn\'t support that.',
            },
          },
        ],
      },
    ]
    const details = pickTimelineSteps({ transcript, spans: stored })
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(details).toEqual(CREATE_STATUS)
    expect(details.some((msg) => msg === "ps say to avoid files")).toBe(false)
    expect(details.join("\n")).not.toContain("its ste, run a merge script")
    expect(details.join("\n").split("its steps say to avoid files").length - 1).toBe(1)
  })

  it("drops fragment-only stored copies when JSONL cannot be rebuilt", () => {
    const intact = CREATE_STATUS[2]
    const hole = intact.replace(
      "its steps say to avoid files, run a merge script",
      "its ste, run a merge script"
    )
    const details = pickTimelineSteps({
      transcript: "",
      spans: [
        {
          name: "gen_ai.assistant",
          attributes: [
            {
              key: "gen_ai.assistant.message",
              value: { stringValue: "ps say to avoid files" },
            },
          ],
        },
        {
          name: "tool.shell",
          attributes: [
            {
              key: "gen_ai.tool.call.arguments",
              value: { stringValue: "extract_text.py" },
            },
          ],
        },
        {
          name: "gen_ai.assistant",
          attributes: [
            { key: "gen_ai.assistant.message", value: { stringValue: hole } },
          ],
        },
        {
          name: "gen_ai.assistant",
          attributes: [
            { key: "gen_ai.assistant.message", value: { stringValue: intact } },
          ],
        },
      ],
    })
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(details).toEqual([intact])
  })

  it("rebuilds stored spliced assistant JSONL to the two completed messages", () => {
    const transcript = readFileSync(
      join(
        dirname(fileURLToPath(import.meta.url)),
        "../../../tests/fixtures/stored_spliced_assistant.jsonl"
      ),
      "utf8"
    )
    const first =
      "The script exited cleanly but printed nothing, so I'll confirm the output file was actually written."
    const second = JSON.parse(transcript.trim().split("\n").at(-1) || "{}").message.content[0]
      .text as string
    const details = pickTimelineSteps({
      transcript,
      spans: [
        {
          name: "gen_ai.assistant",
          attributes: [
            {
              key: "gen_ai.assistant.message",
              value: { stringValue: "aned and salin`). The result:" },
            },
          ],
        },
      ],
    })
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(details).toEqual([first, second])
    expect(details.some((msg) => msg.startsWith("aned"))).toBe(false)
    expect(details.join("\n")).not.toContain("Londonleanly")
    expect(details.some((msg) => msg.includes("cleved"))).toBe(false)
  })

  it("keeps live text when a later turn has no completed event", () => {
    const first =
      "The script exited cleanly but printed nothing, so I'll confirm the output file was actually written."
    const live = "Still writing the cleaned table, waiting on the sandbox."
    const transcript = [
      JSON.stringify({
        type: "assistant",
        message: { content: [{ type: "text", text: first }] },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 2,
        message: {
          content: [{ type: "text", text: "leanly but printed nothing, so I'll confirm" }],
        },
      }),
      JSON.stringify({
        type: "tool_call",
        subtype: "started",
        tool_call: { shellToolCall: { args: { command: "ls output/" } } },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 3,
        message: { content: [{ type: "text", text: "Still writing the cleaned" }] },
      }),
      JSON.stringify({
        type: "assistant",
        timestamp_ms: 4,
        message: { content: [{ type: "text", text: " table, waiting on the sandbox." }] },
      }),
    ].join("\n")
    const details = pickTimelineSteps({ transcript })
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(details).toEqual([first, live])
  })

  it("drops stored splice and hole copies when JSONL is absent", () => {
    const first =
      "The script exited cleanly but printed nothing, so I'll confirm the output file was actually written."
    const transcript = readFileSync(
      join(
        dirname(fileURLToPath(import.meta.url)),
        "../../../tests/fixtures/stored_spliced_assistant.jsonl"
      ),
      "utf8"
    )
    const second = JSON.parse(transcript.trim().split("\n").at(-1) || "{}").message.content[0]
      .text as string
    const splice =
      "aned and salin`). The result:\n\n```\nname,age,city\nAda,36,Londonleanly but printed nothing, so I'll confirm the output file was actually written."
    const hole = second
      .replace("cleaned and saved", "cleved")
      .replace("Cara,,Berlin", "Cara,,Ber")
    const details = pickTimelineSteps({
      transcript: "",
      spans: [
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: splice } }],
        },
        {
          name: "tool.shell",
          attributes: [
            { key: "gen_ai.tool.call.arguments", value: { stringValue: "ls output/" } },
          ],
        },
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: hole } }],
        },
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: first } }],
        },
        {
          name: "gen_ai.assistant",
          attributes: [{ key: "gen_ai.assistant.message", value: { stringValue: second } }],
        },
      ],
    })
      .filter((step) => step.title === "Assistant")
      .map((step) => step.detail || "")
    expect(details).toEqual([first, second])
  })
})

describe("previewPlainText / truncateAtWord", () => {
  it("strips backticks and asterisks then cuts on a word boundary", () => {
    const text =
      "I pulled the text out of hello.pdf and saved it to `output/extracted.txt` after running the *pdf* skill."
    const preview = truncateAtWord(previewPlainText(text), 72)
    expect(preview.includes("`")).toBe(false)
    expect(preview.includes("*")).toBe(false)
    expect(preview.endsWith("…")).toBe(true)
    expect(preview).not.toMatch(/extracted\.$/)
  })
})

describe("spansToTimelineSteps titles", () => {
  it("does not show Run · PdfReader('hello.pdf')", () => {
    const steps = spansToTimelineSteps([
      {
        name: "tool.shell",
        attributes: [
          {
            key: "gen_ai.tool.call.arguments",
            value: { stringValue: "PdfReader('hello.pdf')" },
          },
        ],
      },
    ])
    expect(steps[0]?.title).toBe("Read hello.pdf")
    expect(steps[0]?.title).not.toMatch(/Run ·/)
  })

  it("uses Agent step instead of Harness step", () => {
    const steps = spansToTimelineSteps([
      {
        name: "tool.shell",
        attributes: [
          {
            key: "gen_ai.tool.call.arguments",
            value: { stringValue: "SKILLGATE_TASK=merge do-the-thing" },
          },
        ],
      },
    ])
    expect(steps[0]?.title).not.toMatch(/Harness/i)
    expect(JSON.stringify(steps)).not.toMatch(/SKILLGATE_TASK/)
  })
})

describe("llm harness RUN steps", () => {
  const transcript = [
    "selected: pdf",
    'RUN: python3 .skillgate/skills/pdf/scripts/create_pdf.py --title "Q3 Status" output/status.pdf',
    "ran python3 .skillgate/skills/pdf/scripts/create_pdf.py --title Q3 Status output/status.pdf exit=2",
  ].join("\n")

  it("shows RUN commands even when the only span is eval.check", () => {
    const steps = pickTimelineSteps({
      transcript,
      spans: [{ name: "eval.check" }],
    })
    expect(steps.length).toBeGreaterThan(0)
    const blob = JSON.stringify(steps)
    expect(blob).toMatch(/create_pdf/)
    expect(blob).not.toMatch(/No agent steps/)
  })
})
