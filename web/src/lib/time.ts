export function absoluteTime(value?: string | null): string | undefined {
  if (!value) {
    return undefined
  }
  const then = Date.parse(value)
  if (Number.isNaN(then)) {
    return undefined
  }
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(then)
}

export function relativeTime(value?: string | null): string {
  if (!value) {
    return "—"
  }
  const then = Date.parse(value)
  if (Number.isNaN(then)) {
    return "—"
  }
  const seconds = Math.max(0, Math.round((Date.now() - then) / 1000))
  if (seconds < 45) {
    return "just now"
  }
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) {
    return `${minutes}m ago`
  }
  const hours = Math.round(minutes / 60)
  if (hours < 24) {
    return `${hours}h ago`
  }
  const days = Math.round(hours / 24)
  if (days < 30) {
    return `${days}d ago`
  }
  return value.slice(0, 10)
}
