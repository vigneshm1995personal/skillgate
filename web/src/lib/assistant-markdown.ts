export type MdInline =
  | { type: "text"; text: string }
  | { type: "code"; text: string }
  | { type: "strong"; text: string }

export type MdBlock =
  | { type: "p"; children: MdInline[] }
  | { type: "ul"; items: MdInline[][] }
  | { type: "pre"; text: string }

const FENCE = /```[a-zA-Z0-9_-]*\n?([\s\S]*?)```/g
const INLINE = /(`[^`]+`|\*\*[^*]+\*\*)/g

function parseInline(text: string): MdInline[] {
  const parts: MdInline[] = []
  const src = text.replace(/\r\n/g, "\n")
  let last = 0
  const re = new RegExp(INLINE.source, "g")
  let match: RegExpExecArray | null
  while ((match = re.exec(src))) {
    if (match.index > last) {
      parts.push({ type: "text", text: src.slice(last, match.index) })
    }
    const token = match[0]
    if (token.startsWith("`")) {
      parts.push({ type: "code", text: token.slice(1, -1) })
    } else {
      parts.push({ type: "strong", text: token.slice(2, -2) })
    }
    last = match.index + token.length
  }
  if (last < src.length) {
    parts.push({ type: "text", text: src.slice(last) })
  }
  return parts.length ? parts : [{ type: "text", text: src }]
}

function parseProse(text: string): MdBlock[] {
  const lines = text.replace(/\r\n/g, "\n").split("\n")
  const blocks: MdBlock[] = []
  let para: string[] = []
  let bullets: string[] = []

  const flushPara = () => {
    const blob = para.join(" ").trim()
    para = []
    if (blob) blocks.push({ type: "p", children: parseInline(blob) })
  }
  const flushUl = () => {
    if (!bullets.length) return
    blocks.push({ type: "ul", items: bullets.map((item) => parseInline(item)) })
    bullets = []
  }

  for (const raw of lines) {
    const bullet = raw.match(/^\s*[-*]\s+(.+)$/)
    if (bullet) {
      flushPara()
      bullets.push(bullet[1])
      continue
    }
    if (!raw.trim()) {
      flushPara()
      flushUl()
      continue
    }
    flushUl()
    para.push(raw.trim())
  }
  flushPara()
  flushUl()
  return blocks
}

/** Tokenize assistant prose. Callers render React nodes — never raw HTML. */
export function parseAssistantMarkdown(src: string): MdBlock[] {
  const text = src.replace(/\r\n/g, "\n")
  if (!text.trim()) return []
  const blocks: MdBlock[] = []
  let last = 0
  const fence = new RegExp(FENCE.source, "g")
  let match: RegExpExecArray | null
  while ((match = fence.exec(text))) {
    if (match.index > last) {
      blocks.push(...parseProse(text.slice(last, match.index)))
    }
    blocks.push({ type: "pre", text: (match[1] || "").replace(/\n$/, "") })
    last = match.index + match[0].length
  }
  if (last < text.length) {
    blocks.push(...parseProse(text.slice(last)))
  }
  return blocks
}
