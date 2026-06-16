import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { CalendarDays, Plus, ChevronRight } from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { sisApi } from '@/lib/api/sis'
import type { ExamSessionOut } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------

function SessionStatusBadge({ status }: { status: string }) {
  const map: Record<string, { label: string; color: string; bg: string; border: string }> = {
    DRAFT:             { label: 'Draft',             color: '#94a3b8', bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.2)' },
    PUBLISHED:         { label: 'Published',         color: '#60a5fa', bg: 'rgba(59,130,246,0.12)',  border: 'rgba(59,130,246,0.25)' },
    SEATING_ALLOCATED: { label: 'Seating Allocated', color: '#a78bfa', bg: 'rgba(139,92,246,0.12)', border: 'rgba(139,92,246,0.25)' },
    LOCKED:            { label: 'Locked',            color: '#fbbf24', bg: 'rgba(251,191,36,0.12)', border: 'rgba(251,191,36,0.25)' },
    COMPLETED:         { label: 'Completed',         color: '#4ade80', bg: 'rgba(34,197,94,0.12)',  border: 'rgba(34,197,94,0.25)' },
  }
  const s = map[status] ?? { label: status, color: '#94a3b8', bg: 'rgba(148,163,184,0.1)', border: 'rgba(148,163,184,0.2)' }
  return (
    <span className="inline-flex items-center text-xs px-2 py-0.5 rounded font-semibold"
      style={{ background: s.bg, color: s.color, border: `1px solid ${s.border}` }}>
      {s.label}
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    REGULAR: '#60a5fa', SUPPLEMENTARY: '#fbbf24', REVALUATION: '#f87171', IMPROVEMENT: '#a78bfa',
  }
  const color = colors[type] ?? '#94a3b8'
  return (
    <span className="text-[10px] font-bold uppercase tracking-wide" style={{ color }}>{type}</span>
  )
}

// ---------------------------------------------------------------------------
// Create session modal
// ---------------------------------------------------------------------------

function CreateSessionModal({
  onClose, onCreated,
}: { onClose: () => void; onCreated: (id: string) => void }) {
  const [form, setForm] = useState({
    semester_id: '',
    session_type: 'REGULAR',
    session_name: '',
    academic_year: new Date().getFullYear() + '-' + (new Date().getFullYear() + 1),
    start_date: '',
    end_date: '',
    notes: '',
  })
  const [error, setError] = useState<string | null>(null)

  const semestersQ = useQuery({
    queryKey: ['semesters-all'],
    queryFn: () => academicsApi.listSemesters(),
  })

  const create = useMutation({
    mutationFn: () => sisApi.createExamSession({
      semester_id: form.semester_id,
      session_type: form.session_type,
      session_name: form.session_name,
      academic_year: form.academic_year,
      start_date: form.start_date,
      end_date: form.end_date,
      notes: form.notes || undefined,
    }),
    onSuccess: (data) => onCreated(data.id),
    onError: (e: any) => setError(e.response?.data?.detail?.message ?? 'Failed to create session'),
  })

  const set = (k: string, v: string) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-[480px] rounded-2xl border border-white/10 bg-[#0f1e3d] p-6 shadow-2xl">
        <h3 className="text-base font-bold text-white mb-4">Create Exam Session</h3>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Semester</label>
            <Select value={form.semester_id || undefined} onValueChange={v => set('semester_id', v)}>
              <SelectTrigger className="w-full"><SelectValue placeholder="— Select semester —" /></SelectTrigger>
              <SelectContent>
                {(semestersQ.data ?? []).map(s => (
                  <SelectItem key={s.id} value={s.id}>Sem {s.number}{s.label ? ` — ${s.label}` : ''}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Session Type</label>
              <Select value={form.session_type} onValueChange={v => set('session_type', v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {['REGULAR', 'SUPPLEMENTARY', 'REVALUATION', 'IMPROVEMENT'].map(t => (
                    <SelectItem key={t} value={t}>{t}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Academic Year</label>
              <input type="text" value={form.academic_year} onChange={e => set('academic_year', e.target.value)}
                placeholder="2025-26"
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Session Name</label>
            <input type="text" value={form.session_name} onChange={e => set('session_name', e.target.value)}
              placeholder="e.g. End Semester Examination Dec 2025"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Start Date</label>
              <input type="date" value={form.start_date} onChange={e => set('start_date', e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">End Date</label>
              <input type="date" value={form.end_date} onChange={e => set('end_date', e.target.value)}
                className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500" />
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Notes (optional)</label>
            <textarea rows={2} value={form.notes} onChange={e => set('notes', e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none" />
          </div>
        </div>

        {error && <p className="mt-3 text-xs text-red-400">{error}</p>}

        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => create.mutate()}
            disabled={create.isPending || !form.semester_id || !form.session_name || !form.start_date || !form.end_date}>
            {create.isPending ? 'Creating…' : 'Create Session'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function ExamSessionsPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [showCreate, setShowCreate] = useState(false)
  const [semFilter, setSemFilter] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const sessionsQ = useQuery({
    queryKey: ['exam-sessions', semFilter, statusFilter],
    queryFn: () => sisApi.listExamSessions({
      semester_id: semFilter || undefined,
      status: statusFilter || undefined,
    }),
  })

  const semestersQ = useQuery({
    queryKey: ['semesters-all'],
    queryFn: () => academicsApi.listSemesters(),
  })

  const sessions: ExamSessionOut[] = sessionsQ.data ?? []

  function handleCreated(id: string) {
    qc.invalidateQueries({ queryKey: ['exam-sessions'] })
    setShowCreate(false)
    navigate(`/sis/exam/sessions/${id}`)
  }

  return (
    <PageShell>
      <PageHeader
        title="Exam Sessions"
        icon={CalendarDays}
        action={
          <Button size="sm" onClick={() => setShowCreate(true)}>
            <Plus size={14} className="mr-1" /> New Session
          </Button>
        }
      />

      {/* Filters */}
      <div className="px-6 pt-3 pb-4 border-b border-white/6 flex gap-3 flex-wrap">
        <Select value={semFilter || 'ALL'} onValueChange={v => setSemFilter(v === 'ALL' ? '' : v)}>
          <SelectTrigger className="w-[180px]"><SelectValue placeholder="All Semesters" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All Semesters</SelectItem>
            {(semestersQ.data ?? []).map(s => (
              <SelectItem key={s.id} value={s.id}>Sem {s.number}{s.label ? ` — ${s.label}` : ''}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select value={statusFilter || 'ALL'} onValueChange={v => setStatusFilter(v === 'ALL' ? '' : v)}>
          <SelectTrigger className="w-[180px]"><SelectValue placeholder="All Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="ALL">All Status</SelectItem>
            {['DRAFT', 'PUBLISHED', 'SEATING_ALLOCATED', 'LOCKED', 'COMPLETED'].map(s => (
              <SelectItem key={s} value={s}>{s}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* List */}
      <div className="px-6 py-6">
        {sessionsQ.isLoading && <p className="text-sm text-slate-500">Loading…</p>}

        {sessions.length === 0 && !sessionsQ.isLoading && (
          <div className="flex flex-col items-center justify-center py-20 text-slate-500">
            <CalendarDays size={36} className="mb-3 opacity-30" />
            <p className="text-sm">No exam sessions found.</p>
            <p className="text-xs mt-1 text-slate-600">Click New Session to get started.</p>
          </div>
        )}

        <div className="space-y-3">
          {sessions.map(s => (
            <div key={s.id}
              className="rounded-xl border border-white/8 bg-white/4 p-4 hover:bg-white/6 transition-colors cursor-pointer"
              onClick={() => navigate(`/sis/exam/sessions/${s.id}`)}>
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <TypeBadge type={s.session_type} />
                    <SessionStatusBadge status={s.status} />
                  </div>
                  <h3 className="text-base font-bold text-white mt-1 truncate">{s.session_name}</h3>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {s.academic_year} · {s.start_date} → {s.end_date}
                  </p>
                  <p className="text-xs text-slate-500 mt-1">
                    {s.schedule_count} schedule{s.schedule_count !== 1 ? 's' : ''}
                  </p>
                </div>
                <ChevronRight size={16} className="text-slate-500 flex-shrink-0 mt-1" />
              </div>
            </div>
          ))}
        </div>
      </div>

      {showCreate && (
        <CreateSessionModal onClose={() => setShowCreate(false)} onCreated={handleCreated} />
      )}
    </PageShell>
  )
}
