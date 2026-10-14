import { useRef, useState } from "react"
import { UploadIcon } from "lucide-react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Spinner } from "@/components/ui/spinner"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, ApiError } from "@/lib/api"

export type ImportRow = {
  row: number
  id: string
  prompt: string
  action: string
  error?: string | null
}

type Props = {
  skillId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  onImported?: () => void
}

export function DatasetImportDialog({
  skillId,
  open,
  onOpenChange,
  onImported,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [busy, setBusy] = useState(false)
  const [rows, setRows] = useState<ImportRow[]>([])
  const [format, setFormat] = useState<string | null>(null)
  const [warnings, setWarnings] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [ready, setReady] = useState(false)

  const reset = () => {
    setFile(null)
    setRows([])
    setFormat(null)
    setWarnings([])
    setError(null)
    setReady(false)
    if (inputRef.current) {
      inputRef.current.value = ""
    }
  }

  const preview = async (picked: File) => {
    setBusy(true)
    setError(null)
    setReady(false)
    try {
      const data = await api.importDataset({
        skill: skillId,
        file: picked,
        dryRun: true,
        onConflict: "fail",
      })
      setRows(data.rows || [])
      setFormat(data.format || null)
      setWarnings(data.warnings || [])
      const hasErrors = (data.rows || []).some((row) => row.error)
      setReady(!hasErrors && (data.imported_count || 0) > 0)
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message)
        const extra = err as ApiError & { rows?: ImportRow[] }
        if (extra.rows?.length) {
          setRows(extra.rows)
        }
      } else {
        setError(err instanceof Error ? err.message : "Could not read that file.")
      }
    } finally {
      setBusy(false)
    }
  }

  const confirm = async () => {
    if (!file) {
      return
    }
    setBusy(true)
    setError(null)
    try {
      await api.importDataset({
        skill: skillId,
        file,
        dryRun: false,
        confirm: true,
        onConflict: "fail",
      })
      onImported?.()
      onOpenChange(false)
      reset()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          reset()
        }
        onOpenChange(next)
      }}
    >
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Import dataset</DialogTitle>
          <DialogDescription>
            Upload CSV, JSONL, or YAML. Rows are validated before anything is
            saved to this skill.
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.tsv,.jsonl,.ndjson,.yaml,.yml"
              className="sr-only"
              id="dataset-import-file"
              onChange={(event) => {
                const picked = event.target.files?.[0]
                setFile(picked ?? null)
                if (picked) {
                  void preview(picked)
                }
              }}
            />
            <Button
              type="button"
              variant="outline"
              disabled={busy}
              onClick={() => inputRef.current?.click()}
            >
              <UploadIcon data-icon="inline-start" />
              Choose file
            </Button>
            {file ? (
              <span className="text-sm text-muted-foreground">{file.name}</span>
            ) : null}
            {busy ? <Spinner className="size-4" /> : null}
          </div>
          {format ? (
            <p className="text-sm text-muted-foreground">
              Detected {format.toUpperCase()} · {rows.length} row
              {rows.length === 1 ? "" : "s"}
            </p>
          ) : null}
          {error ? (
            <Alert variant="destructive">
              <AlertTitle>Could not import</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}
          {warnings.length > 0 ? (
            <ul className="list-disc pl-5 text-sm text-muted-foreground">
              {warnings.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          ) : null}
          {rows.length > 0 ? (
            <div className="max-h-64 overflow-auto rounded-lg border">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-12">#</TableHead>
                    <TableHead>Id</TableHead>
                    <TableHead>Prompt</TableHead>
                    <TableHead>Action</TableHead>
                    <TableHead>Error</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.row}>
                      <TableCell>{row.row}</TableCell>
                      <TableCell className="font-mono text-xs">{row.id}</TableCell>
                      <TableCell className="max-w-[12rem] truncate text-sm">
                        {row.prompt}
                      </TableCell>
                      <TableCell className="text-sm">{row.action}</TableCell>
                      <TableCell className="text-sm text-destructive">
                        {row.error || ""}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            disabled={busy || !ready}
            onClick={() => void confirm()}
          >
            {busy ? <Spinner data-icon="inline-start" /> : null}
            Import checks
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
