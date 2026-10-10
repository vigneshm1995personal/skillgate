"use client"

import { useEffect, useState } from "react"

import type { LiveState } from "@/lib/types"

/**
 * Seconds the running check has been going, ticking every second.
 *
 * Hosted GETs return `started_at` (server UTC) for the running check; tick
 * locally from it so "Elapsed" never shows a dash or freezes between polls.
 * Falls back to the server's `elapsed_sec` snapshot.
 */
export function useTickingElapsed(live?: LiveState | null): number | null {
  const startedMs = live?.started_at ? Date.parse(live.started_at) : Number.NaN
  const hasStart = Number.isFinite(startedMs)
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!hasStart) {
      return
    }
    const id = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(id)
  }, [hasStart])
  if (hasStart) {
    const local = Math.max(0, (now - startedMs) / 1000)
    // Guard against client clock skew: never show less than the server value.
    const server = live?.elapsed_sec ?? 0
    return Math.max(local, server)
  }
  return live?.elapsed_sec ?? null
}
