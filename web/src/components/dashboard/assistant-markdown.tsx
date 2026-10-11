import type { ReactNode } from "react"

import { parseAssistantMarkdown, type MdInline } from "@/lib/assistant-markdown"

function Inline({ nodes }: { nodes: MdInline[] }) {
  return nodes.map((node, index) => {
    if (node.type === "code") {
      return (
        <code
          key={index}
          className="rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]"
        >
          {node.text}
        </code>
      )
    }
    if (node.type === "strong") {
      return <strong key={index}>{node.text}</strong>
    }
    return <span key={index}>{node.text}</span>
  })
}

export function AssistantMarkdown({ text }: { text: string }) {
  const blocks = parseAssistantMarkdown(text)
  if (!blocks.length) {
    return null
  }
  const parts: ReactNode[] = blocks.map((block, index) => {
    if (block.type === "pre") {
      return (
        <pre
          key={index}
          className="max-h-40 max-w-full overflow-auto rounded-md border bg-muted/40 p-2 font-mono text-[11px] leading-relaxed whitespace-pre-wrap"
        >
          {block.text}
        </pre>
      )
    }
    if (block.type === "ul") {
      return (
        <ul key={index} className="my-1 list-disc space-y-0.5 pl-4">
          {block.items.map((item, itemIndex) => (
            <li key={itemIndex}>
              <Inline nodes={item} />
            </li>
          ))}
        </ul>
      )
    }
    return (
      <p key={index} className="my-1">
        <Inline nodes={block.children} />
      </p>
    )
  })
  return (
    <div className="text-[11px] leading-relaxed break-words text-muted-foreground">
      {parts}
    </div>
  )
}
