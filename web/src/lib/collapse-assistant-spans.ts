/** Lockstep leftover/collapse with skillgate_ai.spans (JSONL + stored-span paths). */

import type { OtlpSpan } from "@/lib/types"

export const LEFTOVER_PREFIX_MIN = 8
const SUBSTRING_MIN = 12
const SHARED_PREFIX_MIN = 32
const HOLE_PREFIX_MIN = 12
const WINDOW = 12
const CONTAIN_MIN = 0.55
/** Near-copy mix leftovers against joined completed texts / longer splices. */
const HOLE_CONTAIN_MIN = 0.85
/** Longer splice wrapping intact n-grams (sibling path only). */
const SPLICE_CONTAIN_MIN = 0.25

function spanAttrs(span: OtlpSpan): Record<string, string> {
  const out: Record<string, string> = {}
  for (const item of span.attributes ?? []) {
    const key = item.key
    const value = item.value
    if (!key || !value) continue
    if (value.stringValue != null) out[key] = value.stringValue
    else if (value.intValue != null) out[key] = String(value.intValue)
    else if (value.doubleValue != null) out[key] = String(value.doubleValue)
    else if (value.boolValue != null) out[key] = String(value.boolValue)
  }
  return out
}

export function assistantMessage(span: OtlpSpan | undefined): string {
  return span ? spanAttrs(span)["gen_ai.assistant.message"] ?? "" : ""
}

function sharedPrefixLen(left: string, right: string): number {
  const n = Math.min(left.length, right.length)
  let i = 0
  while (i < n && left[i] === right[i]) i += 1
  return i
}

function windowContainment(fragment: string, intact: string, window = WINDOW): number {
  if (!fragment || !intact) return 0
  if (fragment.length < window) return intact.includes(fragment) ? 1 : 0
  let hits = 0
  let total = 0
  const step = Math.max(1, Math.floor(window / 2))
  let i = 0
  let last = -1
  while (i <= fragment.length - window) {
    total += 1
    last = i
    if (intact.includes(fragment.slice(i, i + window))) hits += 1
    i += step
  }
  const tail = fragment.length - window
  if (tail > last) {
    total += 1
    if (intact.includes(fragment.slice(tail))) hits += 1
  }
  return total ? hits / total : 0
}

function startsMidToken(text: string): boolean {
  const lead = text.trimStart()[0] ?? ""
  return lead === lead.toLowerCase() && lead !== lead.toUpperCase()
}

function asciiAlnum(ch: string): boolean {
  return /^[A-Za-z0-9]$/.test(ch)
}

/** True when ``left`` and ``right`` share a prefix that splits inside a token. */
function divergesMidWord(left: string, right: string): boolean {
  const n = sharedPrefixLen(left, right)
  if (n < HOLE_PREFIX_MIN || n >= Math.min(left.length, right.length)) return false
  return asciiAlnum(left[n - 1] ?? "") && (asciiAlnum(left[n] ?? "") || asciiAlnum(right[n] ?? ""))
}

/** Stolen from the middle of a word in ``intact``. Phrase reuse at a boundary is not leftover. */
function midWordSteal(fragment: string, intact: string): boolean {
  if (fragment.length < SUBSTRING_MIN || !intact.includes(fragment)) return false
  const idx = intact.indexOf(fragment)
  if (idx <= 0) return false
  return asciiAlnum(intact[idx - 1] ?? "")
}

export function sameTurnText(fragment: string, completed: string): boolean {
  if (!fragment || !completed) return false
  if (fragment === completed) return true
  if (completed.startsWith(fragment) || fragment.startsWith(completed)) return true
  if (completed.endsWith(fragment) || fragment.endsWith(completed)) return true
  return false
}

/** Replay/suffix/mid-string of a completed message. Used on token deltas. */
export function leftoverOfCompleted(fragment: string, completed: string): boolean {
  if (!fragment || !completed) return false
  if (fragment === completed) return true
  if (fragment.startsWith(completed)) return true
  if (completed.endsWith(fragment) && fragment.length >= 4) return true
  if (completed.startsWith(fragment) && fragment.length >= LEFTOVER_PREFIX_MIN) return true
  return midWordSteal(fragment, completed)
}

function isToolSpan(span: OtlpSpan): boolean {
  const name = span.name || ""
  return name.startsWith("tool.") || name === "skill.select"
}

function wrapsNgram(fragment: string, intact: string): boolean {
  if (!fragment || !intact || fragment === intact) return false
  const n = SHARED_PREFIX_MIN
  if (intact.length < n) return windowContainment(intact, fragment) >= CONTAIN_MIN
  const step = Math.max(1, Math.floor(n / 2))
  for (let i = 0; i <= intact.length - n; i += step) {
    if (fragment.includes(intact.slice(i, i + n))) return true
  }
  return fragment.includes(intact.slice(-n))
}

function prefixAcrossTool(fragment: string, intact: string, betweenTool: boolean): boolean {
  if (!betweenTool) return false
  const shorter = fragment.length <= intact.length ? fragment : intact
  const longer = fragment.length <= intact.length ? intact : fragment
  return longer.startsWith(shorter) && shorter.length >= LEFTOVER_PREFIX_MIN
}

/** Replay, suffix, substring, or hole-y copy of one completed text. */
function leftoverOfOneText(fragment: string, intact: string): boolean {
  if (!fragment || !intact || fragment === intact) return false
  if (fragment.startsWith(intact) && fragment.length > intact.length) {
    return windowContainment(fragment, intact) >= CONTAIN_MIN
  }
  if (leftoverOfCompleted(fragment, intact)) return true
  // Hole-y copies share an opening then split inside a word. Unique turns that
  // share an opening then diverge at a word/punctuation boundary stay.
  return divergesMidWord(fragment, intact) && windowContainment(fragment, intact) >= CONTAIN_MIN
}

/** Longer damaged copy wrapping intact bits; not a clean sentence extension. */
function splicedLonger(fragment: string, intact: string): boolean {
  const contain = windowContainment(fragment, intact)
  if (fragment.startsWith(intact)) return contain >= HOLE_CONTAIN_MIN
  if (intact.length >= SUBSTRING_MIN && fragment.includes(intact)) {
    return startsMidToken(fragment) || contain >= HOLE_CONTAIN_MIN
  }
  if (contain >= HOLE_CONTAIN_MIN) return true
  if (contain >= CONTAIN_MIN) return startsMidToken(fragment)
  return contain >= SPLICE_CONTAIN_MIN && wrapsNgram(fragment, intact) && startsMidToken(fragment)
}

/**
 * Stored-span leftover when JSONL completed texts are absent.
 * Shorter: hole/substring of a longer intact sibling.
 * Longer: mid-token splice wrapping intact n-grams.
 * A true prefix/extension across a tool stays.
 */
function leftoverFragment(fragment: string, intact: string, betweenTool: boolean): boolean {
  if (!fragment || !intact || fragment === intact) return false
  if (prefixAcrossTool(fragment, intact, betweenTool)) return false
  if (fragment.length < intact.length) return leftoverOfOneText(fragment, intact)
  return splicedLonger(fragment, intact)
}

/** JSONL completed-texts path. Mixes use ordered join, not sibling splice rules. */
function leftoverOfCompletedTexts(fragment: string, completed: string[]): boolean {
  if (!fragment || !completed.length) return false
  if (completed.some((text) => leftoverOfOneText(fragment, text))) return true
  const contain = windowContainment(fragment, completed.join("\n"))
  if (contain >= HOLE_CONTAIN_MIN) {
    // Mix/glue near-copies are not a substring of any one completed text.
    // Word-boundary phrase reuse of one completed message is a live new turn.
    if (completed.some((text) => text.includes(fragment))) return false
    return true
  }
  return startsMidToken(fragment) && contain >= CONTAIN_MIN
}

export function collapseAssistantSpans(spans: OtlpSpan[], completedTexts?: string[]): OtlpSpan[] {
  const assistant: number[] = []
  spans.forEach((span, idx) => {
    if (span.name === "gen_ai.assistant") assistant.push(idx)
  })
  const drop = new Set<number>()
  const seen = new Map<string, number>()
  const completedList = [...new Set((completedTexts ?? []).map((text) => text.trim()).filter(Boolean))]
  const completedSet = new Set(completedList)
  for (const i of assistant) {
    const msg = assistantMessage(spans[i]).trim()
    if (!msg) {
      drop.add(i)
      continue
    }
    if (seen.has(msg)) {
      drop.add(i)
      continue
    }
    seen.set(msg, i)
  }
  for (const i of assistant) {
    if (drop.has(i)) continue
    const msg = assistantMessage(spans[i]).trim()
    if (completedList.length) {
      if (completedSet.has(msg)) continue
      if (leftoverOfCompletedTexts(msg, completedList)) drop.add(i)
      continue
    }
    for (const j of assistant) {
      if (i === j || drop.has(j)) continue
      const other = assistantMessage(spans[j]).trim()
      const lo = Math.min(i, j)
      const hi = Math.max(i, j)
      let betweenTool = false
      for (let k = lo + 1; k < hi; k += 1) {
        if (spans[k] && isToolSpan(spans[k])) {
          betweenTool = true
          break
        }
      }
      if (leftoverFragment(msg, other, betweenTool)) {
        drop.add(i)
        break
      }
    }
  }
  return spans.filter((_, idx) => !drop.has(idx))
}
