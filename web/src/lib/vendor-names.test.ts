import { readdirSync, readFileSync } from "node:fs"
import { dirname, join, relative } from "node:path"
import { fileURLToPath } from "node:url"
import { describe, expect, it } from "vitest"

const root = join(dirname(fileURLToPath(import.meta.url)), "..")

const BRAND =
  /\b(Codex|Claude|Cursor|OpenAI|Anthropic|OpenRouter|ChatGPT|Vercel|Bedrock|Gemini|Jev|Clef|Cloudflare|AWS)\b/i

function walk(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const next = join(dir, entry.name)
    if (entry.isDirectory()) {
      out.push(...walk(next))
    } else if (/\.(ts|tsx)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) {
      out.push(next)
    }
  }
  return out
}

function stripComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(^|[^:\\])\/\/.*$/gm, "$1")
}

function stringLiterals(source: string): string[] {
  const found: string[] = []
  const quoted = /"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'/g
  const templates = /`(?:\\[\s\S]|[^`\\])*`/g
  for (const match of source.matchAll(quoted)) {
    found.push(match[0].slice(1, -1))
  }
  for (const match of source.matchAll(templates)) {
    found.push(match[0].slice(1, -1))
  }
  return found
}

function jsxText(source: string): string[] {
  const found: string[] = []
  for (const match of source.matchAll(/>([^<>]*)</g)) {
    const text = match[1].replace(/\s+/g, " ").trim()
    if (text && !text.includes("{")) {
      found.push(text)
    }
  }
  return found
}

/**
 * Ids, env keys, and package names stay. Display words do not.
 * Key-source names (which key a decision model takes) are server copy from
 * decision_judges(). This file still rejects those words in UI source.
 */
function renderedResidue(literal: string): string {
  return literal
    .replace(/@[a-z0-9._-]+\/[a-z0-9._-]+/gi, " ")
    .replace(/\b[A-Z][A-Z0-9_]{2,}\b/g, " ")
    .replace(
      /\b(cursor-agent|claude-code|cursor|codex|claude|openai|anthropic|openrouter|jev|clef|cloudflare|vercel|bedrock|aws)\b/g,
      " "
    )
}

describe("rendered UI strings", () => {
  it("does not name a provider or vendor", () => {
    const hits: string[] = []
    for (const file of walk(root)) {
      const text = stripComments(readFileSync(file, "utf8"))
      for (const literal of [...stringLiterals(text), ...jsxText(text)]) {
        const residue = renderedResidue(literal)
        const match = residue.match(BRAND)
        if (match) {
          hits.push(`${relative(root, file)}: ${match[0]} in ${JSON.stringify(literal)}`)
        }
      }
    }
    expect(hits).toEqual([])
  })
})
