export type ImportRow = {
  row: number
  id: string
  prompt: string
  action: string
  error?: string | null
}

export function datasetImportFooter(rows: ImportRow[]): {
  canImport: boolean
  hint: string | null
} {
  if (!rows.length) {
    return { canImport: false, hint: null }
  }
  const errorRows = rows.filter((row) => String(row.error || "").trim())
  if (errorRows.length > 0) {
    const count = errorRows.length
    return {
      canImport: false,
      hint: `Fix ${count} row${count === 1 ? "" : "s"} to import`,
    }
  }
  const importable = rows.filter(
    (row) => row.action !== "skip" && !String(row.error || "").trim()
  )
  if (!importable.length) {
    return { canImport: false, hint: "No rows to import" }
  }
  return { canImport: true, hint: null }
}
