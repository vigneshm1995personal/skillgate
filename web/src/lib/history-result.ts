export function historyResultLabel(passed: boolean | null | undefined): {
  text: string
  tone: "pass" | "fail" | "not-run"
} {
  if (passed === true) {
    return { text: "Pass", tone: "pass" }
  }
  if (passed === false) {
    return { text: "Fail", tone: "fail" }
  }
  return { text: "Not run", tone: "not-run" }
}
