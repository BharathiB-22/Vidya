import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { ChevronRight, ArrowRight, CheckCircle2, AlertTriangle, RefreshCw, Info } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { sisApi } from '@/lib/api/sis'
import type {
  RolloverScope, RolloverScopeIn, RolloverPreviewResponse, RolloverRowOut,
  RolloverCommitResult,
} from '@/lib/api/sis'
import { useQuery } from '@tanstack/react-query'
import { academicsApi } from '@/lib/api/academics'

// ---------------------------------------------------------------------------
// Phase type
// ---------------------------------------------------------------------------
type Phase = 'scope' | 'preview' | 'result'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatusBadge({ status, reason }: { status: 'ready' | 'blocked'; reason: string | null }) {
  if (status === 'ready') {
    return (
      <span
        className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded"
        style={{ background: 'rgba(34,197,94,0.15)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.25)' }}
      >
        <CheckCircle2 size={11} /> ready
      </span>
    )
  }
  return (
    <span
      title={reason ?? undefined}
      className="inline-flex items-center gap-1 text-xs font-semibold px-2 py-0.5 rounded cursor-help"
      style={{ background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.25)' }}
    >
      <AlertTriangle size={11} /> blocked
    </span>
  )
}

function OutcomeBadge({ outcome }: { outcome: 'moved' | 'skipped' | 'error' }) {
  const map = {
    moved:   { bg: 'rgba(34,197,94,0.15)',    color: '#4ade80', label: 'moved' },
    skipped: { bg: 'rgba(148,163,184,0.12)',  color: '#94a3b8', label: 'skipped' },
    error:   { bg: 'rgba(239,68,68,0.12)',    color: '#f87171', label: 'error' },
  }
  const s = map[outcome]
  return (
    <span
      className="inline-flex text-xs font-semibold px-2 py-0.5 rounded"
      style={{ background: s.bg, color: s.color, border: `1px solid ${s.color}33` }}
    >
      {s.label}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Phase 1 — Scope selector
// ---------------------------------------------------------------------------

interface ScopeSelectorProps {
  onPreview: (scope: RolloverScopeIn) => void
  loading: boolean
}

function ScopeSelector({ onPreview, loading }: ScopeSelectorProps) {
  const [scope, setScope] = useState<RolloverScope>('all_programs')
  const [programId, setProgramId] = useState('')
  const [batchId, setBatchId] = useState('')
  const [semesterId, setSemesterId] = useState('')

  const { data: programs = [] } = useQuery({
    queryKey: ['programs-for-rollover'],
    queryFn: () => academicsApi.listPrograms(),
  })

  const { data: batches = [] } = useQuery({
    queryKey: ['batches-for-rollover', programId],
    queryFn: () => academicsApi.listBatches(programId || undefined),
    enabled: scope === 'batch' || scope === 'semester',
  })

  const { data: semesters = [] } = useQuery({
    queryKey: ['semesters-for-rollover', batchId],
    queryFn: () => academicsApi.listSemesters(batchId || undefined),
    enabled: scope === 'semester' && !!batchId,
  })

  const canPreview = (() => {
    if (scope === 'all_programs') return true
    if (scope === 'program') return !!programId
    if (scope === 'batch') return !!batchId
    if (scope === 'semester') return !!semesterId
    return false
  })()

  function buildBody(): RolloverScopeIn {
    const base: RolloverScopeIn = { scope }
    if (scope === 'program' && programId) base.program_id = programId
    if ((scope === 'batch' || scope === 'semester') && batchId) base.batch_id = batchId
    if (scope === 'semester' && semesterId) base.source_semester_id = semesterId
    return base
  }

  return (
    <div
      className="rounded-2xl p-8 max-w-xl mx-auto space-y-6"
      style={{ background: 'rgba(255,255,255,0.03)', border: '1px solid rgba(255,255,255,0.08)' }}
    >
      <div>
        <h2 className="text-base font-semibold text-slate-200 mb-1">Configure Rollover Scope</h2>
        <p className="text-xs text-slate-400">
          Select which students to move. All active students in the selected scope will be
          analysed — preview shows row-level plan before any changes are made.
        </p>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-xs text-slate-400 mb-1.5 font-medium">Scope</label>
          <Select
            value={scope}
            onValueChange={v => {
              setScope(v as RolloverScope)
              setProgramId(''); setBatchId(''); setSemesterId('')
            }}
          >
            <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all_programs">All Programs</SelectItem>
              <SelectItem value="program">By Program</SelectItem>
              <SelectItem value="batch">By Batch</SelectItem>
              <SelectItem value="semester">By Semester (source)</SelectItem>
            </SelectContent>
          </Select>
        </div>

        {(scope === 'program' || scope === 'batch' || scope === 'semester') && (
          <div>
            <label className="block text-xs text-slate-400 mb-1.5 font-medium">Program</label>
            <Select
              value={programId || undefined}
              onValueChange={v => { setProgramId(v); setBatchId(''); setSemesterId('') }}
            >
              <SelectTrigger className="w-full"><SelectValue placeholder="— select program —" /></SelectTrigger>
              <SelectContent>
                {programs.map(p => (
                  <SelectItem key={p.id} value={p.id}>{p.name} ({p.code})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {(scope === 'batch' || scope === 'semester') && (
          <div>
            <label className="block text-xs text-slate-400 mb-1.5 font-medium">Batch</label>
            <Select
              value={batchId || undefined}
              onValueChange={v => { setBatchId(v); setSemesterId('') }}
            >
              <SelectTrigger className="w-full"><SelectValue placeholder="— select batch —" /></SelectTrigger>
              <SelectContent>
                {batches.map(b => (
                  <SelectItem key={b.id} value={b.id}>{b.name} ({b.start_year}–{b.end_year})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}

        {scope === 'semester' && (
          <div>
            <label className="block text-xs text-slate-400 mb-1.5 font-medium">Source Semester</label>
            <Select
              value={semesterId || undefined}
              onValueChange={setSemesterId}
            >
              <SelectTrigger className="w-full"><SelectValue placeholder="— select semester —" /></SelectTrigger>
              <SelectContent>
                {semesters.map(s => (
                  <SelectItem key={s.id} value={s.id}>
                    Semester {s.number}{s.label ? ` — ${s.label}` : ''}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        )}
      </div>

      <div
        className="rounded-lg p-3 flex gap-2 text-xs text-slate-400"
        style={{ background: 'rgba(99,102,241,0.08)', border: '1px solid rgba(99,102,241,0.2)' }}
      >
        <Info size={14} className="shrink-0 mt-0.5 text-indigo-400" />
        Students move from Semester N → Semester N+1 in the same batch. Section name must match
        (e.g. "Section A" → "Section A"). Missing target sections are shown as <strong>blocked</strong>.
      </div>

      <Button
        onClick={() => onPreview(buildBody())}
        disabled={!canPreview || loading}
        className="w-full"
        style={{ background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' }}
      >
        {loading ? (
          <><RefreshCw size={14} className="animate-spin mr-2" />Analysing...</>
        ) : (
          <><ChevronRight size={14} className="mr-2" />Preview Rollover</>
        )}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Phase 2 — Preview table
// ---------------------------------------------------------------------------

interface PreviewPhaseProps {
  preview: RolloverPreviewResponse
  onBack: () => void
  onCommit: () => void
  committing: boolean
}

function PreviewPhase({ preview, onBack, onCommit, committing }: PreviewPhaseProps) {
  const { summary, rows } = preview
  const hasReady = summary.ready > 0

  return (
    <div className="space-y-5">
      {/* Summary banner */}
      <div className="flex flex-wrap gap-3">
        <div
          className="rounded-xl px-5 py-3 flex-1 min-w-[140px]"
          style={{ background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.25)' }}
        >
          <p className="text-xs text-slate-400">Total</p>
          <p className="text-2xl font-bold text-indigo-300">{summary.total}</p>
        </div>
        <div
          className="rounded-xl px-5 py-3 flex-1 min-w-[140px]"
          style={{ background: 'rgba(34,197,94,0.08)', border: '1px solid rgba(34,197,94,0.2)' }}
        >
          <p className="text-xs text-slate-400">Ready to move</p>
          <p className="text-2xl font-bold text-green-400">{summary.ready}</p>
        </div>
        <div
          className="rounded-xl px-5 py-3 flex-1 min-w-[140px]"
          style={{ background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.2)' }}
        >
          <p className="text-xs text-slate-400">Blocked</p>
          <p className="text-2xl font-bold text-yellow-400">{summary.blocked}</p>
        </div>
      </div>

      {summary.blocked > 0 && (
        <div
          className="rounded-lg p-3 flex gap-2 text-xs text-yellow-300"
          style={{ background: 'rgba(251,191,36,0.07)', border: '1px solid rgba(251,191,36,0.2)' }}
        >
          <AlertTriangle size={14} className="shrink-0 mt-0.5" />
          {summary.blocked} student{summary.blocked > 1 ? 's' : ''} will be skipped — target section missing or
          inactive. Hover the <strong>blocked</strong> badge to see the reason.
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'rgba(255,255,255,0.04)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
              {['Student', 'Program / Batch', 'Current Section', 'Target Section', 'Status'].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-400 whitespace-nowrap">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row: RolloverRowOut) => (
              <tr
                key={row.enrollment_id}
                style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
                className="hover:bg-white/[0.02] transition-colors"
              >
                <td className="px-4 py-3">
                  <p className="text-slate-200 font-medium text-xs">{row.student_name}</p>
                  <p className="text-slate-500 text-xs">{row.student_email}</p>
                </td>
                <td className="px-4 py-3 text-xs text-slate-400">
                  <p>{row.program_name}</p>
                  <p className="text-slate-500">{row.batch_name}</p>
                </td>
                <td className="px-4 py-3 text-xs text-slate-300 whitespace-nowrap">
                  Sem {row.current_semester_number} / {row.current_section_name}
                </td>
                <td className="px-4 py-3 text-xs text-slate-300 whitespace-nowrap">
                  {row.target_section_name
                    ? <>Sem {row.target_semester_number} / {row.target_section_name}</>
                    : <span className="text-slate-500 italic">— not found —</span>
                  }
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={row.status} reason={row.reason} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between pt-1">
        <Button variant="ghost" onClick={onBack} className="text-slate-400 hover:text-slate-200">
          ← Back
        </Button>
        <Button
          onClick={onCommit}
          disabled={!hasReady || committing}
          style={hasReady ? { background: 'linear-gradient(135deg,#6366f1,#8b5cf6)' } : {}}
        >
          {committing ? (
            <><RefreshCw size={14} className="animate-spin mr-2" />Moving students…</>
          ) : (
            <>Confirm Rollover <ArrowRight size={14} className="ml-2" /></>
          )}
        </Button>
      </div>

      {!hasReady && (
        <p className="text-center text-xs text-slate-500">No students are ready to move — all are blocked.</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Phase 3 — Result
// ---------------------------------------------------------------------------

function ResultPhase({ result, onDone }: { result: RolloverCommitResult; onDone: () => void }) {
  return (
    <div className="space-y-5 max-w-2xl mx-auto">
      <div
        className="rounded-2xl p-6 text-center"
        style={{ background: 'rgba(34,197,94,0.07)', border: '1px solid rgba(34,197,94,0.2)' }}
      >
        <CheckCircle2 size={40} className="mx-auto mb-3 text-green-400" />
        <h2 className="text-lg font-semibold text-slate-200 mb-1">Rollover Complete</h2>
        <p className="text-xs text-slate-400">
          {result.moved} student{result.moved !== 1 ? 's' : ''} moved
          {result.skipped > 0 ? ` · ${result.skipped} skipped` : ''}
          {result.errors > 0 ? ` · ${result.errors} errors` : ''}
        </p>
      </div>

      {/* Result rows */}
      <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid rgba(255,255,255,0.08)' }}>
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: 'rgba(255,255,255,0.04)', borderBottom: '1px solid rgba(255,255,255,0.08)' }}>
              {['Student', 'Outcome', 'Note'].map(h => (
                <th key={h} className="px-4 py-3 text-left text-xs font-semibold text-slate-400">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map(row => (
              <tr
                key={row.enrollment_id}
                style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}
                className="hover:bg-white/[0.02]"
              >
                <td className="px-4 py-3 text-xs text-slate-200">{row.student_name}</td>
                <td className="px-4 py-3"><OutcomeBadge outcome={row.outcome} /></td>
                <td className="px-4 py-3 text-xs text-slate-400">{row.reason ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex justify-center">
        <Button onClick={onDone} variant="outline" className="border-slate-600 text-slate-300">
          Done
        </Button>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function SemesterRolloverPage() {
  const [phase, setPhase] = useState<Phase>('scope')
  const [scopeBody, setScopeBody] = useState<RolloverScopeIn | null>(null)
  const [preview, setPreview] = useState<RolloverPreviewResponse | null>(null)
  const [commitResult, setCommitResult] = useState<RolloverCommitResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const previewMut = useMutation({
    mutationFn: (body: RolloverScopeIn) => sisApi.rolloverPreview(body),
    onSuccess: (data) => {
      setPreview(data)
      setError(null)
      setPhase('preview')
    },
    onError: () => setError('Preview failed — check server logs.'),
  })

  const commitMut = useMutation({
    mutationFn: (body: RolloverScopeIn) => sisApi.rolloverCommit(body),
    onSuccess: (data) => {
      setCommitResult(data)
      setError(null)
      setPhase('result')
    },
    onError: () => setError('Commit failed — check server logs.'),
  })

  function handlePreview(body: RolloverScopeIn) {
    setScopeBody(body)
    previewMut.mutate(body)
  }

  function handleCommit() {
    if (scopeBody) commitMut.mutate(scopeBody)
  }

  function handleDone() {
    setPhase('scope')
    setScopeBody(null)
    setPreview(null)
    setCommitResult(null)
    setError(null)
  }

  const scopeSuffix = scopeBody
    ? ` — ${{ all_programs: 'All Programs', program: 'By Program', batch: 'By Batch', semester: 'By Semester' }[scopeBody.scope]}`
    : ''

  return (
    <PageShell>
      <PageHeader
        icon={RefreshCw}
        title={`Semester Rollover${scopeSuffix}`}
        subtitle="Move active students from their current semester sections to the next semester"
      />

      {/* Breadcrumb steps */}
      <div className="flex items-center gap-2 mb-8 text-xs text-slate-500">
        {(['scope', 'preview', 'result'] as Phase[]).map((p, i) => (
          <span key={p} className="flex items-center gap-2">
            {i > 0 && <ChevronRight size={12} />}
            <span className={phase === p ? 'text-indigo-400 font-semibold' : ''}>
              {p === 'scope' ? '1. Scope' : p === 'preview' ? '2. Preview' : '3. Done'}
            </span>
          </span>
        ))}
      </div>

      {error && (
        <div
          className="mb-5 rounded-lg p-3 flex gap-2 text-sm text-red-300"
          style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}
        >
          <AlertTriangle size={16} className="shrink-0 mt-0.5" />
          {error}
        </div>
      )}

      {phase === 'scope' && (
        <ScopeSelector onPreview={handlePreview} loading={previewMut.isPending} />
      )}

      {phase === 'preview' && preview && (
        <PreviewPhase
          preview={preview}
          onBack={() => setPhase('scope')}
          onCommit={handleCommit}
          committing={commitMut.isPending}
        />
      )}

      {phase === 'result' && commitResult && (
        <ResultPhase result={commitResult} onDone={handleDone} />
      )}
    </PageShell>
  )
}
