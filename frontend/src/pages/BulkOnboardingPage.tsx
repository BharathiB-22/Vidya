import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Users, Upload, Download, CheckCircle2, XCircle, AlertCircle,
  ChevronDown, ChevronUp, Plus,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { getAdminErrorMessage } from '@/lib/adminApi'
import {
  onboardingApi,
  type CSVCommitResult,
  type CSVPreviewResponse,
  type CSVRowResult,
  type GenerateStudentsResult,
} from '@/lib/api/onboarding'

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-lg bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
      {message}
    </div>
  )
}

function SuccessBanner({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-green-50 border border-green-200 px-4 py-3 text-sm text-green-800 flex items-start gap-2">
      <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5 text-green-600" />
      <div>{children}</div>
    </div>
  )
}

function StatCard({ label, value, color = 'gray' }: { label: string; value: number; color?: 'gray' | 'green' | 'red' | 'amber' }) {
  const colors = {
    gray: 'bg-gray-50 text-gray-700 border-gray-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
  }
  return (
    <div className={`rounded-lg border px-4 py-3 text-center ${colors[color]}`}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs font-medium mt-0.5">{label}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CSV Preview table
// ---------------------------------------------------------------------------

function PreviewTable({ data }: { data: CSVPreviewResponse }) {
  const [showAll, setShowAll] = useState(false)
  const displayRows = showAll ? data.rows : data.rows.slice(0, 20)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-3">
        <StatCard label="Total rows" value={data.total_rows} />
        <StatCard label="Valid" value={data.valid_rows} color="green" />
        <StatCard label="Invalid" value={data.invalid_rows} color={data.invalid_rows > 0 ? 'red' : 'gray'} />
        <StatCard label="Will be created" value={data.valid_rows} color="green" />
      </div>

      {data.rows.length > 0 && (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-600 w-12">#</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Name</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Email</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Identifier</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600 w-24">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {displayRows.map((row) => (
                <PreviewRow key={row.row_number} row={row} />
              ))}
            </tbody>
          </table>
          {data.rows.length > 20 && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="w-full py-2 text-xs text-gray-500 hover:bg-gray-50 flex items-center justify-center gap-1"
            >
              {showAll ? (
                <><ChevronUp className="h-3 w-3" /> Show less</>
              ) : (
                <><ChevronDown className="h-3 w-3" /> Show all {data.rows.length} rows</>
              )}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function PreviewRow({ row }: { row: CSVRowResult }) {
  return (
    <tr className={row.is_valid ? '' : 'bg-red-50'}>
      <td className="px-3 py-2 text-gray-400">{row.row_number}</td>
      <td className="px-3 py-2 text-gray-800">{row.full_name || <span className="text-gray-400 italic">—</span>}</td>
      <td className="px-3 py-2 text-gray-700 font-mono text-xs">{row.email || <span className="text-gray-400 italic">—</span>}</td>
      <td className="px-3 py-2 text-gray-600 font-mono text-xs">{row.identifier || <span className="text-gray-400">—</span>}</td>
      <td className="px-3 py-2">
        {row.is_valid ? (
          <span className="inline-flex items-center gap-1 text-green-700">
            <CheckCircle2 className="h-3.5 w-3.5" /> Valid
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-red-600" title={row.errors.join('; ')}>
            <XCircle className="h-3.5 w-3.5" />
            <span className="text-xs">{row.errors[0]}</span>
          </span>
        )}
      </td>
    </tr>
  )
}

// ---------------------------------------------------------------------------
// Commit result summary
// ---------------------------------------------------------------------------

function CommitSummary({ result }: { result: CSVCommitResult }) {
  const [showErrors, setShowErrors] = useState(false)
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Total processed" value={result.total} />
        <StatCard label="Created" value={result.created} color="green" />
        <StatCard label="Skipped" value={result.skipped} color={result.skipped > 0 ? 'amber' : 'gray'} />
      </div>
      {result.errors.length > 0 && (
        <div className="border border-amber-200 rounded-lg overflow-hidden">
          <button
            onClick={() => setShowErrors(!showErrors)}
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
// File drop zone
// ---------------------------------------------------------------------------

function DropZone({
  file,
  onChange,
  disabled,
}: {
  file: File | null
  onChange: (f: File) => void
  disabled?: boolean
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f?.name.endsWith('.csv')) onChange(f)
  }

  return (
    <div
      onClick={() => !disabled && inputRef.current?.click()}
      onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      className={`border-2 border-dashed rounded-lg px-6 py-8 text-center cursor-pointer transition-colors ${
        disabled ? 'opacity-50 cursor-not-allowed border-gray-200' :
        dragging ? 'border-indigo-400 bg-indigo-50' :
        file ? 'border-green-400 bg-green-50' :
        'border-gray-300 hover:border-indigo-400 hover:bg-gray-50'
      }`}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        className="hidden"
        disabled={disabled}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onChange(f) }}
      />
      <Upload className={`h-8 w-8 mx-auto mb-2 ${file ? 'text-green-500' : 'text-gray-400'}`} />
      {file ? (
        <p className="text-sm font-medium text-green-700">{file.name}</p>
      ) : (
        <>
          <p className="text-sm font-medium text-gray-700">Drop CSV here or click to browse</p>
          <p className="text-xs text-gray-400 mt-1">Max 5 MB</p>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 1: Generate Students
// ---------------------------------------------------------------------------

function GenerateStudentsTab() {
  const [form, setForm] = useState({
    usn_prefix: '',
    program_code: '',
    batch_year: '',
    section: '',
    count: '30',
    start_seq: '1',
    seq_width: '3',
    email_domain: '',
    default_password: 'Student@123',
  })
  const [result, setResult] = useState<GenerateStudentsResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  function set(key: string, val: string) {
    setForm((f) => ({ ...f, [key]: val }))
    setResult(null)
    setError(null)
  }

  // Live USN preview
  const sampleUSN = form.usn_prefix && form.program_code && form.batch_year
    ? `${form.usn_prefix.toUpperCase()}${String(form.batch_year).padStart(2, '0')}${form.program_code.toUpperCase()}${'1'.padStart(Number(form.seq_width) || 3, '0')}`
    : null

  const generateMut = useMutation({
    mutationFn: () =>
      onboardingApi.generateStudents({
        usn_prefix: form.usn_prefix.trim(),
        program_code: form.program_code.trim(),
        batch_year: Number(form.batch_year),
        section: form.section.trim() || undefined,
        count: Number(form.count),
        start_seq: Number(form.start_seq),
        seq_width: Number(form.seq_width),
        email_domain: form.email_domain.trim(),
        default_password: form.default_password,
      }),
    onSuccess: (data) => { setResult(data); setError(null) },
    onError: (err: unknown) => setError(getAdminErrorMessage(err)),
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setResult(null)
    setError(null)
    generateMut.mutate()
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Institution code (USN prefix) *</label>
          <Input value={form.usn_prefix} onChange={(e) => set('usn_prefix', e.target.value)}
            placeholder="ABC" required maxLength={10} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Program code *</label>
          <Input value={form.program_code} onChange={(e) => set('program_code', e.target.value)}
            placeholder="MCA" required maxLength={10} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Batch year (2-digit) *</label>
          <Input type="number" value={form.batch_year} onChange={(e) => set('batch_year', e.target.value)}
            placeholder="26" required min={1} max={99} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Section (optional)</label>
          <Input value={form.section} onChange={(e) => set('section', e.target.value)}
            placeholder="A" maxLength={5} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Number of students *</label>
          <Input type="number" value={form.count} onChange={(e) => set('count', e.target.value)}
            required min={1} max={500} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Starting sequence</label>
          <Input type="number" value={form.start_seq} onChange={(e) => set('start_seq', e.target.value)}
            min={1} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Sequence digit width</label>
          <Input type="number" value={form.seq_width} onChange={(e) => set('seq_width', e.target.value)}
            min={2} max={4} />
        </div>
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Email domain *</label>
          <Input value={form.email_domain} onChange={(e) => set('email_domain', e.target.value)}
            placeholder="university.edu" required maxLength={100} />
        </div>
        <div className="col-span-2 space-y-1">
          <label className="text-xs font-medium text-gray-600">Default password</label>
          <Input value={form.default_password} onChange={(e) => set('default_password', e.target.value)}
            placeholder="Student@123" required minLength={8} />
          <p className="text-xs text-gray-400">All generated students use this password. They will be forced to change it on first login.</p>
        </div>
      </div>

      {sampleUSN && (
        <div className="rounded-lg bg-indigo-50 border border-indigo-200 px-4 py-2 text-sm text-indigo-800">
          <span className="font-medium">Preview: </span>
          <code className="font-mono">{sampleUSN}</code>
          {' → '}
          <code className="font-mono">{sampleUSN.toLowerCase()}@{form.email_domain || 'domain.edu'}</code>
        </div>
      )}

      {error && <ErrorBox message={error} />}

      {result && (
        <div className="space-y-3">
          <SuccessBanner>
            <p className="font-medium">Generation complete</p>
            <p className="mt-0.5">
              {result.created} student{result.created !== 1 ? 's' : ''} created
              {result.skipped > 0 && `, ${result.skipped} skipped (already exist)`}.
              Default password: <code className="font-mono bg-green-100 px-1 rounded">{result.default_password}</code>
            </p>
          </SuccessBanner>
          {result.duplicate_usns.length > 0 && (
            <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              Skipped USNs (already exist): {result.duplicate_usns.join(', ')}
            </div>
          )}
          <div className="grid grid-cols-3 gap-3">
            <StatCard label="Created" value={result.created} color="green" />
            <StatCard label="Skipped" value={result.skipped} color={result.skipped > 0 ? 'amber' : 'gray'} />
            <StatCard label="Duplicates" value={result.duplicate_usns.length} color={result.duplicate_usns.length > 0 ? 'red' : 'gray'} />
          </div>
        </div>
      )}

      <Button type="submit" disabled={generateMut.isPending}>
        {generateMut.isPending ? 'Generating…' : `Generate ${form.count || '?'} Students`}
      </Button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Tab 2/3: CSV Import (shared for students and faculty)
// ---------------------------------------------------------------------------

type ImportRole = 'students' | 'faculty'

function CSVImportTab({ role }: { role: ImportRole }) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<CSVPreviewResponse | null>(null)
  const [result, setResult] = useState<CSVCommitResult | null>(null)
  const [password, setPassword] = useState(role === 'students' ? 'Student@123' : 'Faculty@123')
  const [error, setError] = useState<string | null>(null)

  function reset() {
    setFile(null)
    setPreview(null)
    setResult(null)
    setError(null)
  }

  const previewMut = useMutation({
    mutationFn: (f: File) =>
      role === 'students' ? onboardingApi.previewStudentsCSV(f) : onboardingApi.previewFacultyCSV(f),
    onSuccess: (data) => { setPreview(data); setError(null) },
    onError: (err: unknown) => setError(getAdminErrorMessage(err)),
  })

  const commitMut = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('No file selected')
      return role === 'students'
        ? onboardingApi.commitStudentsCSV(file, password)
        : onboardingApi.commitFacultyCSV(file, password)
    },
    onSuccess: (data) => { setResult(data); setError(null) },
    onError: (err: unknown) => setError(getAdminErrorMessage(err)),
  })

  function handleFileChange(f: File) {
    setFile(f)
    setPreview(null)
    setResult(null)
    setError(null)
    previewMut.mutate(f)
  }

  const isLoading = previewMut.isPending || commitMut.isPending
  const canCommit = preview && preview.valid_rows > 0 && !result

  if (result) {
    return (
      <div className="space-y-4">
        <SuccessBanner>
          <p className="font-medium">Import complete</p>
          <p className="mt-0.5">
            {result.created} user{result.created !== 1 ? 's' : ''} created.
            Default password: <code className="font-mono bg-green-100 px-1 rounded">{password}</code>
          </p>
        </SuccessBanner>
        <CommitSummary result={result} />
        <Button variant="ghost" onClick={reset}>Import another file</Button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-500">
          {role === 'students'
            ? 'Upload a CSV with columns: full_name, email, identifier (optional), section (optional)'
            : 'Upload a CSV with columns: full_name, email, employee_id (optional), department (optional), designation (optional)'}
        </p>
        <button
          onClick={() =>
            role === 'students'
              ? onboardingApi.downloadSampleStudentsCSV()
              : onboardingApi.downloadSampleFacultyCSV()
          }
          className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
        >
          <Download className="h-3.5 w-3.5" />
          Download sample CSV
        </button>
      </div>

      <DropZone file={file} onChange={handleFileChange} disabled={isLoading} />

      {previewMut.isPending && (
        <p className="text-sm text-gray-500 animate-pulse">Validating rows…</p>
      )}

      {error && <ErrorBox message={error} />}

      {preview && !previewMut.isPending && (
        <>
          <PreviewTable data={preview} />

          {preview.valid_rows > 0 && (
            <div className="space-y-3 pt-2 border-t border-gray-200">
              <div className="space-y-1">
                <label className="text-xs font-medium text-gray-600">Default password for imported users</label>
                <Input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder={role === 'students' ? 'Student@123' : 'Faculty@123'}
                  required
                  minLength={8}
                  className="max-w-xs"
                />
                <p className="text-xs text-gray-400">All imported users will be prompted to change this on first login.</p>
              </div>

              <div className="flex items-center gap-3">
                <Button
                  onClick={() => commitMut.mutate()}
                  disabled={!canCommit || commitMut.isPending}
                >
                  {commitMut.isPending
                    ? 'Importing…'
                    : `Confirm & Import ${preview.valid_rows} ${role === 'students' ? 'Students' : 'Faculty'}`}
                </Button>
                <Button variant="ghost" onClick={reset} disabled={isLoading}>
                  Cancel
                </Button>
              </div>
            </div>
          )}

          {preview.valid_rows === 0 && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              No valid rows found. Fix the errors above and re-upload.
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Master data manager (collapsible panel)
// ---------------------------------------------------------------------------

function MasterDataPanel() {
  const [open, setOpen] = useState(false)
  const [deptName, setDeptName] = useState('')
  const [deptCode, setDeptCode] = useState('')
  const [progName, setProgName] = useState('')
  const [progCode, setProgCode] = useState('')
  const [deptError, setDeptError] = useState<string | null>(null)
  const [progError, setProgError] = useState<string | null>(null)
  const queryClient = useQueryClient()

  const depts = useQuery({ queryKey: ['departments'], queryFn: onboardingApi.listDepartments })
  const progs = useQuery({ queryKey: ['programs'], queryFn: onboardingApi.listPrograms })

  const addDept = useMutation({
    mutationFn: () => onboardingApi.createDepartment({ name: deptName.trim(), code: deptCode.trim() }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['departments'] })
      setDeptName('')
      setDeptCode('')
      setDeptError(null)
    },
    onError: (err: unknown) => setDeptError(getAdminErrorMessage(err)),
  })

  const addProg = useMutation({
    mutationFn: () => onboardingApi.createProgram({ name: progName.trim(), code: progCode.trim() }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['programs'] })
      setProgName('')
      setProgCode('')
      setProgError(null)
    },
    onError: (err: unknown) => setProgError(getAdminErrorMessage(err)),
  })

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-5 py-3 bg-gray-50 hover:bg-gray-100 text-sm font-medium text-gray-700 transition-colors"
      >
        <span className="flex items-center gap-2">
          <Users className="h-4 w-4 text-gray-400" />
          Departments &amp; Programs
        </span>
        {open ? <ChevronUp className="h-4 w-4 text-gray-400" /> : <ChevronDown className="h-4 w-4 text-gray-400" />}
      </button>

      {open && (
        <div className="p-5 grid grid-cols-2 gap-6">
          {/* Departments */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Departments</h4>
            {depts.data && depts.data.length > 0 ? (
              <ul className="space-y-1">
                {depts.data.map((d) => (
                  <li key={d.id} className="flex items-center justify-between text-sm">
                    <span className="text-gray-800">{d.name}</span>
                    <code className="text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600">{d.code}</code>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400 italic">No departments yet.</p>
            )}
            <form
              className="flex gap-2"
              onSubmit={(e) => { e.preventDefault(); addDept.mutate() }}
            >
              <Input
                placeholder="Name"
                value={deptName}
                onChange={(e) => setDeptName(e.target.value)}
                required
                className="flex-1 h-8 text-sm"
              />
              <Input
                placeholder="Code"
                value={deptCode}
                onChange={(e) => setDeptCode(e.target.value)}
                required
                maxLength={20}
                className="w-20 h-8 text-sm"
              />
              <Button type="submit" size="sm" disabled={addDept.isPending}>
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </form>
            {deptError && <p className="text-xs text-red-600">{deptError}</p>}
          </div>

          {/* Programs */}
          <div className="space-y-3">
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Programs</h4>
            {progs.data && progs.data.length > 0 ? (
              <ul className="space-y-1">
                {progs.data.map((p) => (
                  <li key={p.id} className="flex items-center justify-between text-sm">
                    <span className="text-gray-800">{p.name}</span>
                    <code className="text-xs bg-gray-100 px-2 py-0.5 rounded text-gray-600">{p.code}</code>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-xs text-gray-400 italic">No programs yet.</p>
            )}
            <form
              className="flex gap-2"
              onSubmit={(e) => { e.preventDefault(); addProg.mutate() }}
            >
              <Input
                placeholder="Name"
                value={progName}
                onChange={(e) => setProgName(e.target.value)}
                required
                className="flex-1 h-8 text-sm"
              />
              <Input
                placeholder="Code"
                value={progCode}
                onChange={(e) => setProgCode(e.target.value)}
                required
                maxLength={20}
                className="w-20 h-8 text-sm"
              />
              <Button type="submit" size="sm" disabled={addProg.isPending}>
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </form>
            {progError && <p className="text-xs text-red-600">{progError}</p>}
          </div>
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type Tab = 'generate' | 'import-students' | 'import-faculty'

const TABS: { id: Tab; label: string }[] = [
  { id: 'generate',        label: 'Generate Students' },
  { id: 'import-students', label: 'Import Students CSV' },
  { id: 'import-faculty',  label: 'Import Faculty CSV' },
]

export default function BulkOnboardingPage() {
  const [activeTab, setActiveTab] = useState<Tab>('generate')

  return (
    <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Bulk Onboarding</h1>
        <p className="text-sm text-gray-500 mt-1">
          Generate student accounts in bulk or import users via CSV. All accounts require a password change on first login.
        </p>
      </div>

      <MasterDataPanel />

      {/* Tab bar */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-0" aria-label="Tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.id
                  ? 'border-indigo-600 text-indigo-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Tab content */}
      <div className="bg-white rounded-xl border border-gray-200 p-6">
        {activeTab === 'generate' && <GenerateStudentsTab />}
        {activeTab === 'import-students' && <CSVImportTab role="students" />}
        {activeTab === 'import-faculty' && <CSVImportTab role="faculty" />}
      </div>
    </div>
  )
}
