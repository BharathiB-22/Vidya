import { useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Users, Upload, Download, CheckCircle2, XCircle, AlertCircle,
  ChevronDown, ChevronUp, FileSpreadsheet, ArrowRight,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { getAdminErrorMessage } from '@/lib/adminApi'
import {
  onboardingApi,
  type CSVCommitResult,
  type CSVPreviewResponse,
  type CSVRowResult,
  type GenerateStudentsResult,
  type ImportContext,
} from '@/lib/api/onboarding'
import {
  academicsApi,
  type Department,
  type AcadProgram,
  type Batch,
  type Semester,
  type Section,
} from '@/lib/api/academics'

// ---------------------------------------------------------------------------
// Shared types
// ---------------------------------------------------------------------------

interface AcadContext {
  dept: Department | null
  program: AcadProgram | null
  batch: Batch | null
  semester: Semester | null
  section: Section | null
}

function emptyContext(): AcadContext {
  return { dept: null, program: null, batch: null, semester: null, section: null }
}

// ---------------------------------------------------------------------------
// UI primitives
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
    gray:  'bg-gray-50 text-gray-700 border-gray-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    red:   'bg-red-50 text-red-700 border-red-200',
    amber: 'bg-amber-50 text-amber-700 border-amber-200',
  }
  return (
    <div className={`rounded-lg border px-3 py-3 text-center ${colors[color]}`}>
      <p className="text-2xl font-bold">{value}</p>
      <p className="text-xs font-medium mt-0.5 leading-tight">{label}</p>
    </div>
  )
}

const selectCls =
  'w-full rounded-md border border-gray-200 bg-white px-3 py-2 text-sm text-gray-800 ' +
  'focus:border-indigo-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 ' +
  'disabled:cursor-not-allowed disabled:bg-gray-50 disabled:text-gray-400'

// ---------------------------------------------------------------------------
// Cascade academic context selector
// ---------------------------------------------------------------------------

function AcadContextSelector({
  onContextChange,
  showSection = true,
  label = 'Academic context',
}: {
  onContextChange: (ctx: AcadContext) => void
  showSection?: boolean
  label?: string
}) {
  const [ctx, setCtx] = useState<AcadContext>(emptyContext())

  const depts = useQuery({
    queryKey: ['acad-depts-ob'],
    queryFn: () => academicsApi.listDepartments(),
  })
  const programs = useQuery({
    queryKey: ['acad-programs-ob', ctx.dept?.id],
    queryFn: () => academicsApi.listPrograms(ctx.dept?.id),
    enabled: !!ctx.dept,
  })
  const batches = useQuery({
    queryKey: ['acad-batches-ob', ctx.program?.id],
    queryFn: () => academicsApi.listBatches(ctx.program?.id),
    enabled: !!ctx.program,
  })
  const semesters = useQuery({
    queryKey: ['acad-sems-ob', ctx.batch?.id],
    queryFn: () => academicsApi.listSemesters(ctx.batch?.id),
    enabled: !!ctx.batch,
  })
  const sections = useQuery({
    queryKey: ['acad-secs-ob', ctx.semester?.id],
    queryFn: () => academicsApi.listSections(ctx.semester?.id),
    enabled: !!ctx.semester && showSection,
  })

  function update(next: AcadContext) {
    setCtx(next)
    onContextChange(next)
  }

  function pickDept(id: string) {
    const dept = depts.data?.find((d) => d.id === id) ?? null
    update({ dept, program: null, batch: null, semester: null, section: null })
  }
  function pickProgram(id: string) {
    const program = programs.data?.find((p) => p.id === id) ?? null
    update({ ...ctx, program, batch: null, semester: null, section: null })
  }
  function pickBatch(id: string) {
    const batch = batches.data?.find((b) => b.id === id) ?? null
    update({ ...ctx, batch, semester: null, section: null })
  }
  function pickSemester(id: string) {
    const semester = semesters.data?.find((s) => s.id === id) ?? null
    update({ ...ctx, semester, section: null })
  }
  function pickSection(id: string) {
    const section = sections.data?.find((s) => s.id === id) ?? null
    update({ ...ctx, section })
  }

  const noDepts = !depts.isLoading && depts.data?.length === 0
  if (noDepts) {
    return (
      <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 flex items-start gap-2">
        <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
        <span>
          No academic structure found.{' '}
          <a href="/sis/departments" className="font-medium underline">
            Set up Departments and Programs first
          </a>{' '}
          before importing users.
        </span>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</p>
      <div className="grid grid-cols-2 gap-3">
        {/* Department */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Department</label>
          <select
            className={selectCls}
            value={ctx.dept?.id ?? ''}
            onChange={(e) => pickDept(e.target.value)}
          >
            <option value="">— select department —</option>
            {depts.data?.filter((d) => d.is_active).map((d) => (
              <option key={d.id} value={d.id}>{d.name} ({d.code})</option>
            ))}
          </select>
        </div>

        {/* Program */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Program</label>
          <select
            className={selectCls}
            value={ctx.program?.id ?? ''}
            disabled={!ctx.dept}
            onChange={(e) => pickProgram(e.target.value)}
          >
            <option value="">— select program —</option>
            {programs.data?.filter((p) => p.is_active).map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.code})</option>
            ))}
          </select>
        </div>

        {/* Batch */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Batch</label>
          <select
            className={selectCls}
            value={ctx.batch?.id ?? ''}
            disabled={!ctx.program}
            onChange={(e) => pickBatch(e.target.value)}
          >
            <option value="">— select batch —</option>
            {batches.data?.filter((b) => b.is_active).map((b) => (
              <option key={b.id} value={b.id}>{b.name} ({b.start_year}–{b.end_year})</option>
            ))}
          </select>
        </div>

        {/* Semester */}
        <div className="space-y-1">
          <label className="text-xs font-medium text-gray-600">Semester</label>
          <select
            className={selectCls}
            value={ctx.semester?.id ?? ''}
            disabled={!ctx.batch}
            onChange={(e) => pickSemester(e.target.value)}
          >
            <option value="">— select semester —</option>
            {semesters.data?.filter((s) => s.is_active).map((s) => (
              <option key={s.id} value={s.id}>
                Semester {s.number}{s.label ? ` — ${s.label}` : ''}
              </option>
            ))}
          </select>
        </div>

        {/* Section (optional) */}
        {showSection && (
          <div className="col-span-2 space-y-1">
            <label className="text-xs font-medium text-gray-600">
              Section <span className="text-gray-400 font-normal">(optional)</span>
            </label>
            <select
              className={selectCls}
              value={ctx.section?.id ?? ''}
              disabled={!ctx.semester}
              onChange={(e) => pickSection(e.target.value)}
            >
              <option value="">— no section —</option>
              {sections.data?.filter((s) => s.is_active).map((s) => (
                <option key={s.id} value={s.id}>Section {s.name}</option>
              ))}
            </select>
          </div>
        )}
      </div>

      {/* Context summary strip */}
      {ctx.program && (
        <div className="flex items-center gap-1.5 flex-wrap mt-1">
          {ctx.dept && <ContextChip label={ctx.dept.code} />}
          <ArrowRight className="h-3 w-3 text-gray-400" />
          {ctx.program && <ContextChip label={`${ctx.program.code}`} highlight />}
          {ctx.batch && <><ArrowRight className="h-3 w-3 text-gray-400" /><ContextChip label={`${ctx.batch.start_year}`} /></>}
          {ctx.semester && <><ArrowRight className="h-3 w-3 text-gray-400" /><ContextChip label={`Sem ${ctx.semester.number}`} /></>}
          {ctx.section && <><ArrowRight className="h-3 w-3 text-gray-400" /><ContextChip label={`Sec ${ctx.section.name}`} /></>}
        </div>
      )}
    </div>
  )
}

function ContextChip({ label, highlight }: { label: string; highlight?: boolean }) {
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
      highlight ? 'bg-indigo-100 text-indigo-800' : 'bg-gray-100 text-gray-600'
    }`}>
      {label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Preview table
// ---------------------------------------------------------------------------

function PreviewTable({ data }: { data: CSVPreviewResponse }) {
  const [showAll, setShowAll] = useState(false)
  const displayRows = showAll ? data.rows : data.rows.slice(0, 20)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-5 gap-2">
        <StatCard label="Total" value={data.total_rows} />
        <StatCard label="Valid" value={data.valid_rows} color="green" />
        <StatCard label="Invalid" value={data.invalid_rows} color={data.invalid_rows > 0 ? 'red' : 'gray'} />
        <StatCard label="Dup in file" value={data.duplicate_in_file} color={data.duplicate_in_file > 0 ? 'amber' : 'gray'} />
        <StatCard label="Dup in system" value={data.duplicate_in_db} color={data.duplicate_in_db > 0 ? 'amber' : 'gray'} />
      </div>

      {data.rows.length > 0 && (
        <div className="border border-gray-200 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="px-3 py-2 text-left font-medium text-gray-600 w-10">#</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Name</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Email</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600">Identifier</th>
                <th className="px-3 py-2 text-left font-medium text-gray-600 w-28">Status</th>
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
      <td className="px-3 py-2 text-gray-400 text-xs">{row.row_number}</td>
      <td className="px-3 py-2 text-gray-800">{row.full_name || <span className="text-gray-400 italic">—</span>}</td>
      <td className="px-3 py-2 text-gray-700 font-mono text-xs">{row.email || <span className="text-gray-400 italic">—</span>}</td>
      <td className="px-3 py-2 text-gray-600 font-mono text-xs">{row.identifier || <span className="text-gray-400">—</span>}</td>
      <td className="px-3 py-2">
        {row.is_valid ? (
          <span className="inline-flex items-center gap-1 text-green-700 text-xs">
            <CheckCircle2 className="h-3.5 w-3.5" /> Valid
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-red-600 text-xs" title={row.errors.join('; ')}>
            <XCircle className="h-3.5 w-3.5" />
            <span className="truncate max-w-[100px]">{row.errors[0]}</span>
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
// Drop zone (CSV + XLSX)
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

  function accept(f: File) {
    const n = f.name.toLowerCase()
    return n.endsWith('.csv') || n.endsWith('.xlsx')
  }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragging(false)
    const f = e.dataTransfer.files[0]
    if (f && accept(f)) onChange(f)
  }

  const isXlsx = file?.name.toLowerCase().endsWith('.xlsx')

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
        accept=".csv,.xlsx"
        className="hidden"
        disabled={disabled}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) onChange(f) }}
      />
      {isXlsx ? (
        <FileSpreadsheet className="h-8 w-8 mx-auto mb-2 text-green-500" />
      ) : (
        <Upload className={`h-8 w-8 mx-auto mb-2 ${file ? 'text-green-500' : 'text-gray-400'}`} />
      )}
      {file ? (
        <p className="text-sm font-medium text-green-700">{file.name}</p>
      ) : (
        <>
          <p className="text-sm font-medium text-gray-700">Drop CSV or Excel (.xlsx) file here, or click to browse</p>
          <p className="text-xs text-gray-400 mt-1">Max 5 MB · .csv or .xlsx</p>
        </>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Template download bar
// ---------------------------------------------------------------------------

function TemplateDownloadBar({ role }: { role: 'students' | 'faculty' }) {
  return (
    <div className="flex items-center gap-4 flex-wrap">
      <span className="text-xs text-gray-500 font-medium">Download template:</span>
      <button
        onClick={() => role === 'students'
          ? onboardingApi.downloadSampleStudentsCSV()
          : onboardingApi.downloadSampleFacultyCSV()
        }
        className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
      >
        <Download className="h-3.5 w-3.5" /> CSV
      </button>
      <button
        onClick={() => role === 'students'
          ? onboardingApi.downloadSampleStudentsXLSX()
          : onboardingApi.downloadSampleFacultyXLSX()
        }
        className="flex items-center gap-1.5 text-xs text-indigo-600 hover:text-indigo-800 font-medium"
      >
        <FileSpreadsheet className="h-3.5 w-3.5" /> Excel (.xlsx)
      </button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// CSV format guide — required / optional columns + an example header row
// ---------------------------------------------------------------------------

interface CsvFormat {
  required: string[]
  optional: string[]
  example: string
}

function ColChip({ name, required }: { name: string; required?: boolean }) {
  return (
    <code
      className="font-mono text-[11px] px-1.5 py-0.5 rounded border"
      style={
        required
          ? { background: '#EEF2FF', color: '#3730A3', borderColor: '#C7D2FE' }
          : { background: '#F3F4F6', color: '#374151', borderColor: '#E5E7EB' }
      }
    >
      {name}
    </code>
  )
}

function CsvFormatGuide({ fmt }: { fmt: CsvFormat }) {
  return (
    <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 space-y-2">
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="text-xs font-semibold" style={{ color: '#111827' }}>Required:</span>
        {fmt.required.map((c) => <ColChip key={c} name={c} required />)}
      </div>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="text-xs font-semibold" style={{ color: '#111827' }}>Optional:</span>
        {fmt.optional.length
          ? fmt.optional.map((c) => <ColChip key={c} name={c} />)
          : <span className="text-xs" style={{ color: '#6B7280' }}>none</span>}
      </div>
      <div className="flex items-start gap-2">
        <span className="text-xs font-semibold shrink-0 pt-1" style={{ color: '#111827' }}>Example:</span>
        <code className="font-mono text-[11px] bg-white border border-gray-200 rounded px-2 py-1 overflow-x-auto whitespace-pre"
          style={{ color: '#374151' }}>
          {fmt.example}
        </code>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Tab 1: Generate Students
// ---------------------------------------------------------------------------

function GenerateStudentsTab() {
  const [ctx, setCtx] = useState<AcadContext>(emptyContext())
  const [form, setForm] = useState({
    usn_prefix: '',
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

  const program_code = ctx.program?.code ?? ''
  const batch_year_str = ctx.batch ? String(ctx.batch.start_year % 100).padStart(2, '0') : ''

  const sampleUSN =
    form.usn_prefix && program_code && batch_year_str
      ? `${form.usn_prefix.toUpperCase()}${batch_year_str}${program_code}${'1'.padStart(Number(form.seq_width) || 3, '0')}`
      : null

  const canGenerate =
    !!ctx.program && !!ctx.batch && !!form.usn_prefix.trim() && !!form.email_domain.trim()

  const generateMut = useMutation({
    mutationFn: () =>
      onboardingApi.generateStudents({
        usn_prefix:       form.usn_prefix.trim(),
        program_code,
        batch_year:       ctx.batch!.start_year % 100,
        section:          ctx.section?.name,
        section_id:       ctx.section?.id,
        count:            Number(form.count),
        start_seq:        Number(form.start_seq),
        seq_width:        Number(form.seq_width),
        email_domain:     form.email_domain.trim(),
        default_password: form.default_password,
      }),
    onSuccess: (data) => { setResult(data); setError(null) },
    onError: (err: unknown) => setError(getAdminErrorMessage(err)),
  })

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); setResult(null); setError(null); generateMut.mutate() }}
      className="space-y-5"
    >
      {/* Cascade context */}
      <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
        <AcadContextSelector onContextChange={setCtx} showSection />
      </div>

      {!ctx.program && (
        <p className="text-xs text-gray-400 text-center">
          Select Department and Program above to proceed.
        </p>
      )}

      {ctx.program && (
        <>
          {/* Derived context display */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Program code</label>
              <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 font-mono">
                {program_code}
              </div>
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Batch year</label>
              <div className="rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-700 font-mono">
                {batch_year_str || <span className="text-gray-400 italic">— select batch —</span>}
              </div>
            </div>
          </div>

          {/* Manual fields */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Institution code (USN prefix) *</label>
              <Input value={form.usn_prefix} onChange={(e) => set('usn_prefix', e.target.value)}
                placeholder="ABC" required maxLength={10} />
            </div>
            <div className="space-y-1">
              <label className="text-xs font-medium text-gray-600">Email domain *</label>
              <Input value={form.email_domain} onChange={(e) => set('email_domain', e.target.value)}
                placeholder="university.edu" required maxLength={100} />
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
              <label className="text-xs font-medium text-gray-600">Default password</label>
              <Input value={form.default_password} onChange={(e) => set('default_password', e.target.value)}
                placeholder="Student@123" required minLength={8} />
            </div>
          </div>

          {sampleUSN && (
            <div className="rounded-lg bg-indigo-50 border border-indigo-200 px-4 py-2 text-sm text-indigo-800">
              <span className="font-medium">USN preview: </span>
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
                <StatCard label="Enrollments" value={result.enrollments_created} color={result.enrollments_created > 0 ? 'green' : 'gray'} />
              </div>
            </div>
          )}

          <Button type="submit" disabled={!canGenerate || generateMut.isPending}>
            {generateMut.isPending ? 'Generating…' : `Generate ${form.count || '?'} Students`}
          </Button>
        </>
      )}
    </form>
  )
}

// ---------------------------------------------------------------------------
// Tab 2 / 3: Import students or faculty
// ---------------------------------------------------------------------------

type ImportRole = 'students' | 'faculty'

function CSVImportTab({ role }: { role: ImportRole }) {
  const [ctx, setCtx] = useState<AcadContext>(emptyContext())
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

  const importCtx: ImportContext = {
    program_id: ctx.program?.id,
    section_id: ctx.section?.id,
  }

  const previewMut = useMutation({
    mutationFn: (f: File) =>
      role === 'students'
        ? onboardingApi.previewStudentsCSV(f, importCtx)
        : onboardingApi.previewFacultyCSV(f),
    onSuccess: (data) => { setPreview(data); setError(null) },
    onError: (err: unknown) => { setError(getAdminErrorMessage(err)); setPreview(null) },
  })

  const commitMut = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('No file selected')
      return role === 'students'
        ? onboardingApi.commitStudentsCSV(file, password, importCtx)
        : onboardingApi.commitFacultyCSV(file, password)
    },
    onSuccess: (data) => { setResult(data); setError(null) },
    onError: (err: unknown) => setError(getAdminErrorMessage(err)),
  })

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
            {result.enrollments_created > 0 && ` · ${result.enrollments_created} section enrollment${result.enrollments_created !== 1 ? 's' : ''} created.`}
          </p>
        </SuccessBanner>
        <CommitSummary result={result} />
        <Button variant="ghost" onClick={reset}>Import another file</Button>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Academic context */}
      <div className="rounded-lg border border-gray-100 bg-gray-50 p-4">
        {role === 'students' ? (
          <AcadContextSelector
            onContextChange={(c) => { setCtx(c); setPreview(null) }}
            showSection
            label="Assign all imported students to"
          />
        ) : (
          <div className="space-y-2">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Department context</p>
            <DeptOnlySelector />
          </div>
        )}
      </div>

      {/* Template downloads */}
      <TemplateDownloadBar role={role} />

      {/* Column guide */}
      <CsvFormatGuide
        fmt={
          role === 'students'
            ? ctx.program
              ? { required: ['full_name', 'email'], optional: ['identifier'],
                  example: 'full_name,email,identifier' }
              : { required: ['full_name', 'email', 'program_code'],
                  optional: ['identifier', 'batch_year', 'section_name'],
                  example: 'full_name,email,program_code,batch_year,section_name' }
            : { required: ['full_name', 'personal_email'], optional: ['program_codes', 'roles'],
                example: 'full_name,personal_email,program_codes,roles' }
        }
      />
      {role === 'students' && ctx.program && (
        <p className="text-xs" style={{ color: '#6B7280' }}>
          Students will be assigned to the selected program/section above — no
          <code className="font-mono mx-1">program_code</code>column needed.
        </p>
      )}
      {role === 'faculty' && (
        <p className="text-xs" style={{ color: '#6B7280' }}>
          Login is the <code className="font-mono mx-1">personal_email</code>. For FACULTY a
          <code className="font-mono mx-1">faculty_code</code>(e.g. FAC0001) and an
          institution email are generated automatically.
          <code className="font-mono mx-1">roles</code>takes one primary role (FACULTY default, or DEAN / BOARD)
          plus FACULTY-only responsibilities GUIDE / EVALUATOR (pipe-separated, e.g. FACULTY|GUIDE|EVALUATOR).
          DEAN and BOARD are standalone accounts — no faculty code, and they cannot carry responsibilities.
        </p>
      )}

      {/* File upload */}
      <DropZone file={file} onChange={(f) => { setFile(f); setPreview(null); setError(null) }} disabled={isLoading} />

      {/* Validate button (file selected, no preview yet) */}
      {file && !preview && !previewMut.isPending && (
        <Button
          variant="outline"
          onClick={() => { setError(null); previewMut.mutate(file) }}
          disabled={isLoading}
        >
          Validate File
        </Button>
      )}

      {previewMut.isPending && (
        <p className="text-sm text-gray-500 animate-pulse">Validating rows…</p>
      )}

      {error && <ErrorBox message={error} />}

      {preview && !previewMut.isPending && (
        <>
          <PreviewTable data={preview} />

          {preview.valid_rows === 0 && (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              No valid rows found. Fix the errors above and re-upload.
            </div>
          )}

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
                    : `Confirm & Import ${preview.valid_rows} ${role === 'students' ? 'Student' : 'Faculty'}${preview.valid_rows !== 1 ? 's' : ''}`}
                </Button>
                <Button variant="ghost" onClick={reset} disabled={isLoading}>
                  Cancel
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

// Simple dept-only dropdown (faculty context, display only)
function DeptOnlySelector() {
  const [selected, setSelected] = useState('')
  const depts = useQuery({
    queryKey: ['acad-depts-ob'],
    queryFn: () => academicsApi.listDepartments(),
  })
  return (
    <select
      className={selectCls}
      value={selected}
      onChange={(e) => setSelected(e.target.value)}
    >
      <option value="">— filter by department (display only) —</option>
      {depts.data?.filter((d) => d.is_active).map((d) => (
        <option key={d.id} value={d.id}>{d.name} ({d.code})</option>
      ))}
    </select>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

type Tab = 'generate' | 'import-students' | 'import-faculty'

const TABS: { id: Tab; label: string }[] = [
  { id: 'generate',        label: 'Generate Students' },
  { id: 'import-students', label: 'Import Students' },
  { id: 'import-faculty',  label: 'Import Faculty' },
]

export default function BulkOnboardingPage() {
  const [activeTab, setActiveTab] = useState<Tab>('generate')

  return (
    <PageShell width="sm">
      <PageHeader
        icon={Users}
        title="Import Users"
        subtitle="Generate student accounts or import users from CSV and Excel files. All accounts require a password change on first login."
      />

      {/* Tab bar */}
      <div className="border-b border-gray-200">
        <nav className="flex gap-0" aria-label="Import Users tabs">
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

      <div className="bg-white rounded-xl border border-gray-200 p-6">
        {activeTab === 'generate'        && <GenerateStudentsTab />}
        {activeTab === 'import-students' && <CSVImportTab role="students" />}
        {activeTab === 'import-faculty'  && <CSVImportTab role="faculty" />}
      </div>
    </PageShell>
  )
}
