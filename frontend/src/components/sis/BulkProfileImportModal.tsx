import { useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import {
  Upload, Download, FileSpreadsheet,
  CheckCircle2, XCircle, AlertCircle,
  ChevronDown, ChevronUp,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import {
  sisApi,
  type ProfileImportPreviewResponse,
  type ProfileImportRowResult,
  type ProfileImportCommitResult,
} from '@/lib/api/sis'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function getErrorMessage(err: unknown): string {
  if (err && typeof err === 'object' && 'response' in err) {
    const resp = (err as { response?: { data?: { detail?: { message?: string } | string } } }).response
    const detail = resp?.data?.detail
    if (typeof detail === 'object' && detail?.message) return detail.message
    if (typeof detail === 'string') return detail
  }
  if (err instanceof Error) return err.message
  return 'An unexpected error occurred'
}

function StatCard({
  label, value, color = 'gray',
}: { label: string; value: number; color?: 'gray' | 'green' | 'red' | 'amber' }) {
  const cls = {
    gray:  'bg-gray-50 text-gray-700 border-gray-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    red:   'bg-red-50 text-red-700 border-red-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
  }[color]
  return (
    <div className={`rounded-lg border px-3 py-3 text-center ${cls}`}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs font-medium mt-0.5 leading-tight">{label}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Drop zone
// ---------------------------------------------------------------------------

function DropZone({
  file, onChange, disabled,
}: { file: File | null; onChange: (f: File) => void; disabled?: boolean }) {
  const ref = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function accept(f: File) {
    const n = f.name.toLowerCase()
    return n.endsWith('.csv') || n.endsWith('.xlsx')
  }

  const isXlsx = file?.name.toLowerCase().endsWith('.xlsx')

  return (
    <div
      onClick={() => !disabled && ref.current?.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => {
        e.preventDefault(); setDragging(false)
        const f = e.dataTransfer.files[0]
        if (f && accept(f)) onChange(f)
      }}
      className={[
        'border-2 border-dashed rounded-lg px-6 py-8 text-center cursor-pointer transition-colors',
        disabled       ? 'opacity-50 cursor-not-allowed border-gray-200' :
        dragging       ? 'border-indigo-400 bg-indigo-50' :
        file           ? 'border-green-400 bg-green-50' :
                         'border-gray-300 hover:border-indigo-400 hover:bg-gray-50',
      ].join(' ')}
    >
      <input
        ref={ref} type="file" accept=".csv,.xlsx" className="hidden"
        disabled={disabled}
        onChange={e => { const f = e.target.files?.[0]; if (f) onChange(f) }}
      />
      {isXlsx
        ? <FileSpreadsheet className="h-8 w-8 mx-auto mb-2 text-green-500" />
        : <Upload className={`h-8 w-8 mx-auto mb-2 ${file ? 'text-green-500' : 'text-gray-400'}`} />
      }
      {file ? (
        <p className="text-sm font-medium text-green-700">{file.name}</p>
      ) : (
        <>
          <p className="text-sm font-medium text-gray-700">Drop CSV or Excel (.xlsx) here, or click to browse</p>
          <p className="text-xs text-gray-400 mt-1">Max 5 MB · .csv or .xlsx</p>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Template download bar
// ---------------------------------------------------------------------------

function TemplateBar() {
  return (
    <div className="flex items-center gap-4 flex-wrap">
      <span className="text-xs text-gray-500 font-medium">Download template:</span>
      <button
        type="button"
        onClick={() => sisApi.downloadBulkProfileTemplateCsv()}
        className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
      >
        <Download className="h-3.5 w-3.5" /> CSV
      </button>
      <button
        type="button"
        onClick={() => sisApi.downloadBulkProfileTemplateXlsx()}
        className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
      >
        <FileSpreadsheet className="h-3.5 w-3.5" /> Excel (.xlsx)
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Preview table
// ---------------------------------------------------------------------------

function PreviewRow({ row }: { row: ProfileImportRowResult }) {
  return (
    <tr className={row.is_valid ? '' : 'bg-red-50'}>
      <td className="px-3 py-2 text-gray-400 text-xs">{row.row_number}</td>
      <td className="px-3 py-2 text-gray-800 text-xs font-mono truncate max-w-[160px]">
        {row.email || <span className="text-gray-400 italic">—</span>}
      </td>
      <td className="px-3 py-2 text-gray-700 text-xs truncate max-w-[120px]">
        {row.student_name ?? <span className="text-gray-400 italic">not found</span>}
      </td>
      <td className="px-3 py-2 text-gray-600 font-mono text-xs">
        {row.usn ?? <span className="text-gray-400">—</span>}
      </td>
      <td className="px-3 py-2 text-gray-600 text-xs">
        {row.admission_year ?? <span className="text-gray-400">—</span>}
      </td>
      <td className="px-3 py-2">
        {row.is_valid ? (
          <span className="inline-flex items-center gap-1 text-green-700 text-xs">
            <CheckCircle2 className="h-3.5 w-3.5" /> Valid
          </span>
        ) : (
          <span
            className="inline-flex items-center gap-1 text-red-600 text-xs"
            title={row.errors.join('; ')}
          >
            <XCircle className="h-3.5 w-3.5" />
            <span className="truncate max-w-[120px]">{row.errors[0]}</span>
          </span>
        )}
      </td>
    </tr>
  )
}

function PreviewTable({ data }: { data: ProfileImportPreviewResponse }) {
  const [showAll, setShowAll] = useState(false)
  const display = showAll ? data.rows : data.rows.slice(0, 20)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-2">
        <StatCard label="Total rows"   value={data.total_rows} />
        <StatCard label="Valid"        value={data.valid_rows}   color="green" />
        <StatCard label="Invalid"      value={data.invalid_rows} color={data.invalid_rows > 0 ? 'red' : 'gray'} />
        <StatCard label="Not found"    value={data.not_found_in_db} color={data.not_found_in_db > 0 ? 'amber' : 'gray'} />
      </div>

      {(data.duplicate_usn_in_file > 0 || data.duplicate_usn_in_db > 0 || data.duplicate_email_in_file > 0) && (
        <div className="flex gap-3">
          {data.duplicate_email_in_file > 0 && (
            <StatCard label="Dup email in file" value={data.duplicate_email_in_file} color="amber" />
          )}
          {data.duplicate_usn_in_file > 0 && (
            <StatCard label="Dup USN in file"   value={data.duplicate_usn_in_file}   color="amber" />
          )}
          {data.duplicate_usn_in_db > 0 && (
            <StatCard label="USN conflict in DB" value={data.duplicate_usn_in_db}    color="amber" />
          )}
        </div>
      )}

      {data.rows.length > 0 && (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b border-gray-200">
                <tr>
                  <th className="px-3 py-2 text-left font-medium text-gray-600 w-8">#</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Email</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Student</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">USN</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600">Adm. Year</th>
                  <th className="px-3 py-2 text-left font-medium text-gray-600 w-40">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {display.map(row => <PreviewRow key={row.row_number} row={row} />)}
              </tbody>
            </table>
          </div>
          {data.rows.length > 20 && (
            <button
              type="button"
              onClick={() => setShowAll(v => !v)}
              className="w-full py-2 text-xs text-gray-500 hover:bg-gray-50 flex items-center justify-center gap-1"
            >
              {showAll
                ? <><ChevronUp className="h-3 w-3" /> Show less</>
                : <><ChevronDown className="h-3 w-3" /> Show all {data.rows.length} rows</>}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Commit summary
// ---------------------------------------------------------------------------

function CommitSummary({ result }: { result: ProfileImportCommitResult }) {
  const [showErrors, setShowErrors] = useState(false)
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Total processed" value={result.total} />
        <StatCard label="Updated"         value={result.updated} color="green" />
        <StatCard label="Skipped"         value={result.skipped} color={result.skipped > 0 ? 'amber' : 'gray'} />
      </div>
      {result.errors.length > 0 && (
        <div className="border border-amber-200 rounded-lg overflow-hidden">
          <button
            type="button"
            onClick={() => setShowErrors(v => !v)}
            className="w-full flex items-center justify-between px-4 py-2 bg-amber-50 text-sm font-medium text-amber-800"
          >
            <span className="flex items-center gap-2">
              <AlertCircle className="h-4 w-4" />
              {result.errors.length} skipped row{result.errors.length !== 1 ? 's' : ''}
            </span>
            {showErrors ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
          </button>
          {showErrors && (
            <ul className="px-4 py-3 text-xs text-amber-700 space-y-1 bg-white border-t border-amber-100">
              {result.errors.map((e, i) => <li key={i} className="font-mono">{e}</li>)}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main modal
// ---------------------------------------------------------------------------

type Step = 'upload' | 'preview' | 'done'

interface Props {
  open: boolean
  onClose: () => void
  onSuccess: () => void  // triggers directory list refetch
}

export function BulkProfileImportModal({ open, onClose, onSuccess }: Props) {
  const [step, setStep]       = useState<Step>('upload')
  const [file, setFile]       = useState<File | null>(null)
  const [preview, setPreview] = useState<ProfileImportPreviewResponse | null>(null)
  const [result, setResult]   = useState<ProfileImportCommitResult | null>(null)
  const [error, setError]     = useState<string | null>(null)

  function reset() {
    setStep('upload')
    setFile(null)
    setPreview(null)
    setResult(null)
    setError(null)
  }

  function handleClose() {
    reset()
    onClose()
  }

  const previewMut = useMutation({
    mutationFn: (f: File) => sisApi.previewBulkProfileImport(f),
    onSuccess: (data) => {
      setPreview(data)
      setError(null)
      setStep('preview')
    },
    onError: (err) => setError(getErrorMessage(err)),
  })

  const commitMut = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('No file selected')
      return sisApi.commitBulkProfileImport(file)
    },
    onSuccess: (data) => {
      setResult(data)
      setError(null)
      setStep('done')
      onSuccess()
    },
    onError: (err) => setError(getErrorMessage(err)),
  })

  const isLoading = previewMut.isPending || commitMut.isPending
  const canCommit = preview && preview.valid_rows > 0

  return (
    <Dialog open={open} onOpenChange={open ? handleClose : undefined}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center justify-between">
            Import Student Profiles
          </DialogTitle>
        </DialogHeader>

        {/* Step indicator */}
        <div className="flex items-center gap-2 text-xs text-gray-500 -mt-1">
          {(['upload', 'preview', 'done'] as Step[]).map((s, i) => (
            <span key={s} className="flex items-center gap-2">
              {i > 0 && <span className="text-gray-300">›</span>}
              <span className={step === s ? 'text-indigo-600 font-semibold' : ''}>
                {s === 'upload' ? '1. Upload' : s === 'preview' ? '2. Review' : '3. Done'}
              </span>
            </span>
          ))}
        </div>

        <div className="space-y-5 pt-1">

          {/* ── STEP 1: Upload ── */}
          {step === 'upload' && (
            <>
              <TemplateBar />
              <p className="text-xs text-gray-500">
                Required column: <code className="font-mono bg-gray-100 px-1 rounded">email</code>
                {' '}(matches existing student accounts) ·
                Optional: <code className="font-mono bg-gray-100 px-1 rounded">usn</code>,{' '}
                <code className="font-mono bg-gray-100 px-1 rounded">admission_year</code>,{' '}
                phone, address, emergency contact
              </p>
              <DropZone
                file={file}
                onChange={f => { setFile(f); setError(null) }}
                disabled={isLoading}
              />
              {file && !previewMut.isPending && (
                <Button
                  onClick={() => { setError(null); previewMut.mutate(file) }}
                  disabled={isLoading}
                >
                  Validate File
                </Button>
              )}
              {previewMut.isPending && (
                <p className="text-sm text-gray-500 animate-pulse">Validating rows…</p>
              )}
              {error && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}
            </>
          )}

          {/* ── STEP 2: Preview ── */}
          {step === 'preview' && preview && (
            <>
              <PreviewTable data={preview} />

              {preview.valid_rows === 0 && (
                <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  No valid rows found. Fix the errors above and re-upload.
                </div>
              )}

              {error && (
                <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                  {error}
                </div>
              )}

              <div className="flex items-center gap-3 pt-2 border-t border-gray-200">
                {canCommit && (
                  <Button
                    onClick={() => commitMut.mutate()}
                    disabled={!canCommit || commitMut.isPending}
                  >
                    {commitMut.isPending
                      ? 'Updating…'
                      : `Confirm & Update ${preview.valid_rows} Student${preview.valid_rows !== 1 ? 's' : ''}`}
                  </Button>
                )}
                <Button
                  variant="ghost"
                  onClick={reset}
                  disabled={isLoading}
                >
                  ← Back
                </Button>
              </div>
            </>
          )}

          {/* ── STEP 3: Done ── */}
          {step === 'done' && result && (
            <>
              <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800 flex items-start gap-2">
                <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-green-600" />
                <div>
                  <p className="font-medium">Import complete</p>
                  <p className="mt-0.5">
                    {result.updated} student profile{result.updated !== 1 ? 's' : ''} updated.
                    {result.skipped > 0 && ` ${result.skipped} row${result.skipped !== 1 ? 's' : ''} skipped.`}
                  </p>
                </div>
              </div>
              <CommitSummary result={result} />
              <div className="flex items-center gap-3 pt-2 border-t border-gray-200">
                <Button onClick={handleClose}>Close</Button>
                <Button variant="ghost" onClick={reset}>Import another file</Button>
              </div>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
