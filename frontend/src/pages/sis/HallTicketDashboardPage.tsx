import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Ticket, CheckCircle2, XCircle, AlertTriangle, RefreshCw,
  Send, Plus, ChevronRight, Filter, Users,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'
import type { EligibilityOut } from '@/lib/api/sis'
import { academicsApi } from '@/lib/api/academics'

// ---------------------------------------------------------------------------
// Badge helpers
// ---------------------------------------------------------------------------

function EligibilityBadge({ status }: { status: string }) {
  if (status === 'ELIGIBLE')
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded"
        style={{ background: 'rgba(34,197,94,0.12)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.25)' }}>
        <CheckCircle2 size={10} /> Eligible
      </span>
    )
  if (status === 'CONDITIONAL')
    return (
      <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded"
        style={{ background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.25)' }}>
        <AlertTriangle size={10} /> Conditional
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded"
      style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}>
      <XCircle size={10} /> Not Eligible
    </span>
  )
}

function PublishBadge({ status }: { status: string }) {
  const draft = status === 'DRAFT'
  return (
    <span className="inline-flex items-center text-xs px-2 py-0.5 rounded"
      style={{
        background: draft ? 'rgba(148,163,184,0.1)' : 'rgba(59,130,246,0.12)',
        color: draft ? '#94a3b8' : '#60a5fa',
        border: `1px solid ${draft ? 'rgba(148,163,184,0.2)' : 'rgba(59,130,246,0.25)'}`,
      }}>
      {draft ? 'Draft' : 'Published'}
    </span>
  )
}

// ---------------------------------------------------------------------------
// Stat card
// ---------------------------------------------------------------------------

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className="rounded-xl border border-white/8 bg-white/4 px-4 py-3">
      <p className="text-[11px] text-slate-700 uppercase tracking-wide font-semibold">{label}</p>
      <p className="text-2xl font-black mt-0.5" style={{ color }}>{value}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Compute modal
// ---------------------------------------------------------------------------

function ComputeModal({
  semesterId, onClose, onDone,
}: { semesterId: string; onClose: () => void; onDone: () => void }) {
  const [threshold, setThreshold] = useState('75')
  const [error, setError] = useState<string | null>(null)

  const compute = useMutation({
    mutationFn: () => sisApi.computeEligibility({ semester_id: semesterId, threshold_pct: parseFloat(threshold) }),
    onSuccess: () => { onDone(); onClose() },
    onError: (e: any) => setError(e.response?.data?.detail?.message ?? 'Compute failed'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-96 rounded-2xl border border-white/10 bg-[#0f1e3d] p-6 shadow-2xl">
        <h3 className="text-base font-bold text-white mb-4">Compute Eligibility</h3>
        <label className="block text-xs text-slate-400 mb-1">Attendance threshold (%)</label>
        <input
          type="number" min={0} max={100} step={1}
          value={threshold}
          onChange={e => setThreshold(e.target.value)}
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => compute.mutate()} disabled={compute.isPending}>
            {compute.isPending ? 'Computing…' : 'Compute'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Generate batch modal
// ---------------------------------------------------------------------------

function GenerateModal({
  semesterId, onClose, onDone,
}: { semesterId: string; onClose: () => void; onDone: () => void }) {
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)

  const generate = useMutation({
    mutationFn: () => sisApi.generateHallTicketBatch({ semester_id: semesterId, notes: notes || undefined }),
    onSuccess: () => { onDone(); onClose() },
    onError: (e: any) => setError(e.response?.data?.detail?.message ?? 'Generation failed'),
  })

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="w-96 rounded-2xl border border-white/10 bg-[#0f1e3d] p-6 shadow-2xl">
        <h3 className="text-base font-bold text-white mb-1">Generate Hall Tickets</h3>
        <p className="text-xs text-slate-400 mb-4">
          Assigns ticket numbers to all PUBLISHED ELIGIBLE and CONDITIONAL students in this semester.
        </p>
        <label className="block text-xs text-slate-400 mb-1">Notes (optional)</label>
        <textarea
          rows={2} value={notes} onChange={e => setNotes(e.target.value)}
          placeholder="Batch generation note…"
          className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
        />
        {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
        <div className="mt-5 flex justify-end gap-2">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" onClick={() => generate.mutate()} disabled={generate.isPending}>
            {generate.isPending ? 'Generating…' : 'Generate'}
          </Button>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function HallTicketDashboardPage() {
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [semesterId, setSemesterId] = useState('')
  const [statusFilter, setStatusFilter] = useState('')
  const [publishFilter, setPublishFilter] = useState('')
  const [showCompute, setShowCompute] = useState(false)
  const [showGenerate, setShowGenerate] = useState(false)

  const semestersQ = useQuery({
    queryKey: ['semesters-all'],
    queryFn: () => academicsApi.listSemesters(),
  })

  const dashQ = useQuery({
    queryKey: ['ht-dashboard', semesterId, statusFilter, publishFilter],
    queryFn: () => sisApi.getEligibilityDashboard({
      semester_id: semesterId,
      status: statusFilter || undefined,
      publish_status: publishFilter || undefined,
    }),
    enabled: !!semesterId,
  })

  const publish = useMutation({
    mutationFn: () => sisApi.publishEligibility({ semester_id: semesterId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['ht-dashboard', semesterId] }),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey: ['ht-dashboard', semesterId] })

  const dash = dashQ.data
  const rows: EligibilityOut[] = dash?.rows ?? []

  return (
    <PageShell>
      <PageHeader title="Hall Ticket Eligibility" icon={Ticket} />

      {/* Semester picker */}
      <div className="px-6 pt-2 pb-4 border-b border-white/6">
        <div className="flex flex-wrap gap-3 items-center">
          <select
            value={semesterId}
            onChange={e => setSemesterId(e.target.value)}
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500"
          >
            <option value="">— Select semester —</option>
            {(semestersQ.data ?? []).map(s => (
              <option key={s.id} value={s.id}>
                Sem {s.number}{s.label ? ` — ${s.label}` : ''}
              </option>
            ))}
          </select>

          {semesterId && (
            <>
              <Button size="sm" variant="outline" onClick={() => setShowCompute(true)}>
                <RefreshCw size={13} className="mr-1" /> Compute
              </Button>
              <Button size="sm" variant="outline" onClick={() => publish.mutate()} disabled={publish.isPending}>
                <Send size={13} className="mr-1" /> Publish All
              </Button>
              <Button size="sm" onClick={() => setShowGenerate(true)}>
                <Plus size={13} className="mr-1" /> Generate Tickets
              </Button>
            </>
          )}
        </div>
      </div>

      {/* Stats */}
      {dash && (
        <div className="px-6 py-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
          <StatCard label="Total" value={dash.total_students} color="#94a3b8" />
          <StatCard label="Eligible" value={dash.eligible_count} color="#4ade80" />
          <StatCard label="Conditional" value={dash.conditional_count} color="#fbbf24" />
          <StatCard label="Not Eligible" value={dash.not_eligible_count} color="#f87171" />
        </div>
      )}

      {/* Filters */}
      {semesterId && (
        <div className="px-6 pb-3 flex gap-2 flex-wrap">
          <div className="flex items-center gap-1 text-xs text-slate-700">
            <Filter size={11} /> Filter:
          </div>
          {(['', 'ELIGIBLE', 'CONDITIONAL', 'NOT_ELIGIBLE'] as const).map(s => (
            <button key={s}
              onClick={() => setStatusFilter(s)}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
                statusFilter === s
                  ? 'bg-blue-600 text-white border-blue-500'
                  : 'border-white/10 text-slate-800 hover:border-white/20 hover:text-slate-900'
              }`}>
              {s || 'All Status'}
            </button>
          ))}
          {(['', 'DRAFT', 'PUBLISHED'] as const).map(s => (
            <button key={s + 'pub'}
              onClick={() => setPublishFilter(s)}
              className={`px-2.5 py-1 rounded-lg text-xs font-semibold border transition-all ${
                publishFilter === s
                  ? 'bg-blue-600 text-white border-blue-500'
                  : 'border-white/10 text-slate-800 hover:border-white/20 hover:text-slate-900'
              }`}>
              {s || 'All Visibility'}
            </button>
          ))}
        </div>
      )}

      {/* Table */}
      <div className="px-6 pb-8">
        {!semesterId && (
          <div className="flex flex-col items-center justify-center py-20 text-slate-700">
            <Users size={36} className="mb-3 opacity-30" />
            <p className="text-sm">Select a semester to view eligibility</p>
          </div>
        )}

        {semesterId && dashQ.isLoading && (
          <p className="text-sm text-slate-700 py-10 text-center">Loading…</p>
        )}

        {semesterId && dashQ.isError && (
          <p className="text-sm text-red-400 py-10 text-center">Failed to load eligibility data.</p>
        )}

        {rows.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-white/8">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/8 text-left text-[11px] text-slate-700 uppercase tracking-wide">
                  <th className="px-4 py-3 font-semibold">Student</th>
                  <th className="px-4 py-3 font-semibold">USN</th>
                  <th className="px-4 py-3 font-semibold">Attendance</th>
                  <th className="px-4 py-3 font-semibold">Status</th>
                  <th className="px-4 py-3 font-semibold">Visibility</th>
                  <th className="px-4 py-3 font-semibold">Hall Ticket</th>
                  <th className="px-4 py-3 font-semibold"></th>
                </tr>
              </thead>
              <tbody>
                {rows.map(row => (
                  <tr key={row.id}
                    className="border-b border-white/5 hover:bg-white/[0.03] transition-colors">
                    <td className="px-4 py-3">
                      <p className="font-semibold text-white text-[13px]">{row.student_name}</p>
                      <p className="text-[11px] text-slate-700">{row.email}</p>
                    </td>
                    <td className="px-4 py-3 text-slate-900 text-[13px]">{row.usn ?? '—'}</td>
                    <td className="px-4 py-3 text-[13px]">
                      {row.attendance_pct != null ? (
                        <span className={row.has_shortage ? 'text-red-400' : 'text-green-400'}>
                          {Number(row.attendance_pct).toFixed(1)}%
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-3"><EligibilityBadge status={row.status} /></td>
                    <td className="px-4 py-3"><PublishBadge status={row.publish_status} /></td>
                    <td className="px-4 py-3 text-[12px] text-slate-900 font-mono">
                      {row.hall_ticket_number ?? '—'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        onClick={() => navigate(`/sis/hall-tickets/eligibility/${row.id}`)}
                        className="text-blue-400 hover:text-blue-300 flex items-center gap-0.5 text-xs">
                        View <ChevronRight size={12} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {semesterId && !dashQ.isLoading && rows.length === 0 && dash && (
          <div className="flex flex-col items-center justify-center py-16 text-slate-700">
            <Ticket size={32} className="mb-3 opacity-30" />
            <p className="text-sm">No eligibility records found for the selected filters.</p>
            <p className="text-xs mt-1 text-slate-600">Click Compute to run eligibility checks.</p>
          </div>
        )}
      </div>

      {showCompute && semesterId && (
        <ComputeModal semesterId={semesterId} onClose={() => setShowCompute(false)} onDone={invalidate} />
      )}
      {showGenerate && semesterId && (
        <GenerateModal semesterId={semesterId} onClose={() => setShowGenerate(false)} onDone={invalidate} />
      )}
    </PageShell>
  )
}
