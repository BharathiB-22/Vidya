import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  CheckCircle2, XCircle, AlertTriangle, ChevronLeft,
  ShieldCheck, Ticket, Edit3,
} from 'lucide-react'
import { PageShell } from '@/components/shell/PageShell'
import { PageHeader } from '@/components/shell/PageHeader'
import { Button } from '@/components/ui/button'
import { sisApi } from '@/lib/api/sis'

function EligibilityBadge({ status }: { status: string }) {
  if (status === 'ELIGIBLE')
    return (
      <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 rounded-lg font-semibold"
        style={{ background: 'rgba(34,197,94,0.12)', color: '#4ade80', border: '1px solid rgba(34,197,94,0.25)' }}>
        <CheckCircle2 size={14} /> Eligible
      </span>
    )
  if (status === 'CONDITIONAL')
    return (
      <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 rounded-lg font-semibold"
        style={{ background: 'rgba(251,191,36,0.12)', color: '#fbbf24', border: '1px solid rgba(251,191,36,0.25)' }}>
        <AlertTriangle size={14} /> Conditional
      </span>
    )
  return (
    <span className="inline-flex items-center gap-1.5 text-sm px-3 py-1 rounded-lg font-semibold"
      style={{ background: 'rgba(239,68,68,0.12)', color: '#f87171', border: '1px solid rgba(239,68,68,0.25)' }}>
      <XCircle size={14} /> Not Eligible
    </span>
  )
}

function CheckRow({ label, passed, detail }: { label: string; passed: boolean; detail: string }) {
  return (
    <div className="flex items-start gap-3 py-2.5 border-b border-white/5 last:border-0">
      {passed
        ? <CheckCircle2 size={15} className="text-green-400 mt-0.5 flex-shrink-0" />
        : <XCircle size={15} className="text-red-400 mt-0.5 flex-shrink-0" />}
      <div>
        <p className="text-sm font-semibold text-white">{label}</p>
        <p className="text-xs text-slate-400 mt-0.5">{detail}</p>
      </div>
    </div>
  )
}

export default function EligibilityDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [showOverride, setShowOverride] = useState(false)
  const [overrideStatus, setOverrideStatus] = useState<'ELIGIBLE' | 'CONDITIONAL'>('ELIGIBLE')
  const [overrideReason, setOverrideReason] = useState('')
  const [overrideError, setOverrideError] = useState<string | null>(null)

  const q = useQuery({
    queryKey: ['eligibility', id],
    queryFn: () => sisApi.getEligibility(id!),
    enabled: !!id,
  })

  const override = useMutation({
    mutationFn: () => sisApi.overrideEligibility(id!, { status: overrideStatus, reason: overrideReason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['eligibility', id] })
      setShowOverride(false)
      setOverrideReason('')
      setOverrideError(null)
    },
    onError: (e: any) => setOverrideError(e.response?.data?.detail?.message ?? 'Override failed'),
  })

  const row = q.data

  if (q.isLoading)
    return <PageShell><p className="p-8 text-slate-500 text-sm">Loading…</p></PageShell>

  if (!row)
    return <PageShell><p className="p-8 text-red-400 text-sm">Eligibility record not found.</p></PageShell>

  const checks = [
    { label: 'Attendance', passed: !row.has_shortage, detail: row.attendance_pct != null ? `${Number(row.attendance_pct).toFixed(1)}% (threshold: ${row.attendance_threshold_used}%)` : 'Not computed' },
    { label: 'Internal Marks Locked', passed: row.marks_all_locked, detail: row.marks_all_locked ? 'All components locked by faculty' : 'Some mark components are not yet locked' },
    { label: 'Internal Marks Filled', passed: row.marks_all_filled, detail: row.marks_all_filled ? 'All marks entered' : 'Some mark entries are missing' },
  ]

  return (
    <PageShell>
      <PageHeader
        title="Eligibility Detail"
        icon={Ticket}
        action={
          <Button variant="ghost" size="sm" onClick={() => navigate(-1)}>
            <ChevronLeft size={14} className="mr-1" /> Back
          </Button>
        }
      />

      <div className="px-6 py-6 max-w-2xl space-y-5">

        {/* Student info card */}
        <div className="rounded-2xl border border-white/8 bg-white/4 p-5">
          <div className="flex items-start justify-between gap-3 flex-wrap">
            <div>
              <h2 className="text-lg font-bold text-white">{row.student_name}</h2>
              <p className="text-sm text-slate-400 mt-0.5">{row.email}</p>
              {row.usn && <p className="text-xs text-slate-500 mt-0.5 font-mono">{row.usn}</p>}
            </div>
            <EligibilityBadge status={row.override_status ?? row.status} />
          </div>

          <div className="mt-4 grid grid-cols-2 gap-3 text-sm">
            <div>
              <p className="text-[11px] text-slate-500 uppercase tracking-wide mb-0.5">Semester</p>
              <p className="text-white font-semibold">{row.computed_semester_name || '—'}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase tracking-wide mb-0.5">Academic Year</p>
              <p className="text-white font-semibold">{row.computed_academic_year || '—'}</p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase tracking-wide mb-0.5">Publish Status</p>
              <p className={row.publish_status === 'PUBLISHED' ? 'text-blue-400 font-semibold' : 'text-slate-400 font-semibold'}>
                {row.publish_status}
              </p>
            </div>
            <div>
              <p className="text-[11px] text-slate-500 uppercase tracking-wide mb-0.5">Hall Ticket #</p>
              <p className="text-white font-mono font-semibold">{row.hall_ticket_number ?? '—'}</p>
            </div>
          </div>
        </div>

        {/* Checklist */}
        <div className="rounded-2xl border border-white/8 bg-white/4 p-5">
          <h3 className="text-sm font-bold text-white mb-3">Eligibility Checks</h3>
          {checks.map(c => <CheckRow key={c.label} {...c} />)}
          {row.failure_reasons.length > 0 && (
            <div className="mt-3 rounded-lg border border-red-500/20 bg-red-500/8 p-3">
              <p className="text-xs font-semibold text-red-400 mb-1">Failure Reasons</p>
              <ul className="space-y-0.5">
                {row.failure_reasons.map((r, i) => (
                  <li key={i} className="text-xs text-red-300 flex items-start gap-1.5">
                    <span className="text-red-500 mt-0.5">•</span> {r}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Override info */}
        {row.is_overridden && (
          <div className="rounded-2xl border border-amber-500/20 bg-amber-500/8 p-5">
            <div className="flex items-center gap-2 mb-2">
              <ShieldCheck size={14} className="text-amber-400" />
              <p className="text-sm font-bold text-amber-400">Override Applied</p>
            </div>
            <p className="text-xs text-slate-300">
              Status changed to <strong>{row.override_status}</strong> by admin/dean.
            </p>
            {row.override_reason && (
              <p className="text-xs text-slate-400 mt-1 italic">"{row.override_reason}"</p>
            )}
          </div>
        )}

        {/* Override action */}
        <div className="flex gap-2">
          <Button
            variant="outline" size="sm"
            onClick={() => setShowOverride(true)}
            className="border-amber-500/30 text-amber-400 hover:bg-amber-500/10">
            <Edit3 size={13} className="mr-1" /> Override Eligibility
          </Button>
        </div>
      </div>

      {/* Override modal */}
      {showOverride && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
          <div className="w-[450px] rounded-2xl border border-white/10 bg-[#0f1e3d] p-6 shadow-2xl">
            <h3 className="text-base font-bold text-white mb-1">Override Eligibility</h3>
            <p className="text-xs text-slate-400 mb-4">
              This is a human gate action. A mandatory reason must be provided and will be recorded in the audit log.
            </p>

            <label className="block text-xs text-slate-400 mb-1">New Status</label>
            <select
              value={overrideStatus}
              onChange={e => setOverrideStatus(e.target.value as 'ELIGIBLE' | 'CONDITIONAL')}
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500 mb-3"
            >
              <option value="ELIGIBLE">ELIGIBLE</option>
              <option value="CONDITIONAL">CONDITIONAL</option>
            </select>

            <label className="block text-xs text-slate-400 mb-1">Reason (min 20 characters)</label>
            <textarea
              rows={3} value={overrideReason} onChange={e => setOverrideReason(e.target.value)}
              placeholder="Provide a clear justification for this override…"
              className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
            />
            <p className="text-[10px] text-slate-600 mt-0.5">{overrideReason.length}/20 min characters</p>

            {overrideError && <p className="mt-2 text-xs text-red-400">{overrideError}</p>}

            <div className="mt-5 flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => { setShowOverride(false); setOverrideError(null) }}>Cancel</Button>
              <Button
                size="sm"
                onClick={() => override.mutate()}
                disabled={override.isPending || overrideReason.length < 20}
                className="bg-amber-600 hover:bg-amber-500 text-white">
                {override.isPending ? 'Saving…' : 'Apply Override'}
              </Button>
            </div>
          </div>
        </div>
      )}
    </PageShell>
  )
}
